#!/usr/bin/env python2
"""
#python -c "import cyth, doctest; print(doctest.testmod(cyth.cyth_script))"
python -m doctest cyth_script.py
ut
python cyth/cyth_script.py ~/code/fpath
cyth_script.py ~/code/ibeis/ibeis/model/hots
cyth_script.py "~/code/vtool/vtool"

"""
from __future__ import absolute_import, division, print_function
import six
from six.moves import zip, map
from itertools import chain
import utool
import sys
from os.path import isfile
from cyth import cyth_helpers
import ast
#import codegen  # NOQA
import astor
import re
import doctest
import cyth  # NOQA
BASE_CLASS = astor.codegen.SourceGenerator


# See astor/codegen.py for details
# https://github.com/berkerpeksag/astor/blob/master/astor/codegen.py


class CythVisitor(BASE_CLASS):
    indent_level = 0
    emit = sys.stdout.write

    def __init__(self, indent_with=' ' * 4, add_line_information=False,
                 py_modname=None):
        super(CythVisitor, self).__init__(indent_with, add_line_information)
        self.benchmark_names = []
        self.benchmark_codes = []
        self.py_modname = py_modname
        #print('in module ', py_modname)
        self.imported_modules = {}
        self.imported_functions = {}
        #self.all_funcalls = []
        #self.imports_with_usemaps = {}
        self.import_lines = ["cimport cython", "import cython"]
        self.cimport_whitelist = ['numpy']
        self.import_from_blacklist = ['range', 'map', 'zip']
        self.cythonized_funcs = {}
        self.plain_funcs = {}
        self.fpig = FirstpassInformationGatherer()
        self.spig = SecondpassInformationGatherer(self.fpig)

    def get_result(self):
        return '\n'.join(self.import_lines) + '\n' + ''.join(self.result)

    def process_args(self, args, vararg, kwarg, defaults=None):
        processed_argslist = map(self.visit, args)
        if vararg:
            processed_argslist.append('*%s' % vararg)
        if kwarg:
            processed_argslist.append('**%s' % kwarg)
        if defaults is not None:
            first_non_default = len(args) - len(defaults)
            for (ix, de) in enumerate(defaults):
                processed_argslist[first_non_default + ix] += '=%s' % self.visit(defaults[ix])
        return processed_argslist

    def signature(self, node, typedict={}):
        types_minus_sigtypes = typedict.copy()
        want_comma = []

        def write_comma():
            if want_comma:
                self.write(', ')
            else:
                want_comma.append(True)

        def loop_args(args, defaults):
            padding = [None] * (len(args) - len(defaults))
            for arg, default in zip(args, padding + defaults):
                if arg.id in typedict:
                    arg_ = typedict[arg.id] + ' ' + arg.id
                    types_minus_sigtypes.pop(arg.id)
                else:
                    arg_ = arg
                self.write(write_comma, arg_)
                self.conditional_write('=', default)

        loop_args(node.args, node.defaults)
        self.conditional_write(write_comma, '*', node.vararg)
        self.conditional_write(write_comma, '**', node.kwarg)

        kwonlyargs = getattr(node, 'kwonlyargs', None)
        if kwonlyargs:
            if node.vararg is None:
                self.write(write_comma, '*')
            loop_args(kwonlyargs, node.kw_defaults)
        return types_minus_sigtypes

    def parse_cythdef(self, cyth_def):
        """ Hacky string manipulation parsing """
        #ast.literal_eval(utool.unindent(cyth_def))
        typedict = {}
        cdef_mode = False
        current_indent = 0
        for line_ in cyth_def.splitlines():
            indent_level = utool.get_indentation(line_)
            # Check indentation
            if indent_level > current_indent:
                current_indent = indent_level
            elif indent_level > current_indent:
                current_indent = indent_level
                cdef_mode = False
            line = line_.strip()
            if line.startswith('#'):
                continue
            if len(line) == 0:
                continue
            # parse cdef
            if line.startswith('cdef:'):
                cdef_mode = True
                continue
            if cdef_mode or line.startswith('cdef '):
                #def parse_cdef_line(line):
                #    # todo put in better line parsing
                #    # allow for cdef np.array[float, ndims=2] x, y, z
                #    type_ = []
                #    lbrackets = 0
                #    for sub in line.split(','):
                #        sub
                #    pass
                assign_str = line.replace('cdef ', '')
                pos = assign_str.rfind(' ')
                type_ = assign_str[:pos]
                varstr = assign_str[(pos + 1):]
                typedict[varstr] = type_
        return typedict

    def typedict_to_cythdef(self, typedict):
        res = ['cdef:']
        for (id_, type_) in typedict.iteritems():
            #print("%s, %s" % (repr(id_), repr(type_)))
            res.append(self.indent_with + type_ + ' ' + id_)
        if len(typedict) == 0:
            res.append(self.indent_with + 'pass')
        return res

    def parse_cyth_markup(self, docstr, toplevel=False, funcdef_node=None):
        funcname = None if funcdef_node is None else funcdef_node.name
        comment_str = docstr.strip()
        has_markup = comment_str.find('<CYTH') != -1
        # type returned_action = [`defines of string * (string, string) Hashtbl.t | `replace of string] option
        def make_defines(cyth_def, return_type=None):
            typedict = self.parse_cythdef(cyth_def)
            if not return_type:
                return_type = infer_return_type(funcdef_node, typedict)
            return ('defines', cyth_def, typedict, return_type)
        tags_to_actions = [
            ('<CYTH>', lambda cyth_def: make_defines(cyth_def.group(1))),
            ('<CYTH returns="(.*?)">', lambda cyth_def: make_defines(cyth_def.group(2), cyth_def.group(1))),
            ('<CYTH:REPLACE>', lambda cyth_def: ('replace', utool.unindent(cyth_def.group(1)))),
        ]
        end_tag = '</CYTH>'
        regex_flags = re.DOTALL | re.MULTILINE
        regex_to_actions = [(re.compile(tag + '(.*?)' + end_tag, regex_flags), act)
                            for tag, act in tags_to_actions]

        # only return something if CYTH markup was found
        if has_markup:
            if funcname:
                # Parse doctests for benchmarks
                (bench_name, bench_code) = parse_benchmarks(funcname, docstr, self.py_modname)
                self.benchmark_names.append(bench_name)
                self.benchmark_codes.append(bench_code)
            if toplevel:
                # module level cyth-docstrs are always CYTH:REPLACE
                comment_str = re.sub('<CYTH>', '<CYTH:REPLACE>', comment_str)
            for (regex, action) in regex_to_actions:
                match = regex.search(comment_str)
                if match:
                    #cyth_def = match.group(1)
                    return action(match)
            print(comment_str)
            utool.printex(NotImplementedError('no known cyth tag in docstring'),
                           iswarning=True,
                           key_list=[
                               'funcname',
                               'toplevel',
                               'regex',
                               'action',
                               'match',
                               'comment_str'])
        return None

    def visit_Module(self, node):
        # cr = CallRecorder()
        # cr.visit(node)
        # self.all_funcalls = cr.calls
        self.fpig.visit(node)
        self.spig.visit(node)

        def get_alias_name(al):
            alias_name = al.name if al.asname is None else al.asname
            return alias_name

        for subnode in node.body:
            # parse for cythtags
            if is_docstring(subnode):
                #print('Encountered global docstring: %s' % repr(subnode.value.s))
                action = self.parse_cyth_markup(subnode.value.s, toplevel=True)
                if action:
                    if action[0] == 'replace':
                        cyth_def = action[1]
                        self.newline(extra=1)
                        self.write(cyth_def)
            # try to parse functions for cyth tags
            elif isinstance(subnode, ast.FunctionDef):
                self.visit(subnode)
            # register imports
            elif isinstance(subnode, ast.Import):
                for alias in subnode.names:
                    alias_ = get_alias_name(alias)
                    self.imported_modules[alias_] = [alias, False]
            # register from imports
            elif isinstance(subnode, ast.ImportFrom):
                for alias in subnode.names:
                    alias_ = get_alias_name(alias)
                    self.imported_functions[alias_] = [subnode.module, alias, False]
            # register a global
            elif isinstance(subnode, (ast.Assign, ast.AugAssign)):
                targets = assignment_targets(subnode)
                if any((self.spig.globals_used.get(target, False) for target in targets)):
                    self.visit(subnode)
            else:
                #print('Skipping a global %r' % subnode.__class__)
                pass
        imports = self.generate_imports(self.imported_modules, self.imported_functions)
        self.import_lines.extend(imports)
        #return BASE_CLASS.visit_Module(self, node)

    def generate_imports(self, modules, functions):
        imports = []
        for (alias, used_flag) in six.itervalues(modules):
            if used_flag:
                import_line = ast_to_sourcecode(ast.Import(names=[alias]))
                imports.append(import_line)
                if alias.name in self.cimport_whitelist:
                    imports.append('c' + import_line)
        for (modulename, alias, used_flag) in six.itervalues(functions):
            if used_flag and not ((modulename == '__future__') or (alias.name in self.import_from_blacklist)):
                imports.append(ast_to_sourcecode(ast.ImportFrom(module=modulename, names=[alias], level=0)))
        funcs_declared_in_current_module = dict(chain(self.cythonized_funcs.iteritems(), self.plain_funcs.iteritems()))
        called_funcs = []
        #@utool.show_return_value
        def is_called_in(name, node):
            calls = get_funcalls_in_node(node)
            def name_of_call(call):  # ast.Node -> string option
                #print('ast dump: %r' % ast.dump(call))
                if not isinstance(call, ast.Call):
                    return []
                if not isinstance(call.func, ast.Name):
                    return []
                return [call.func.id]
            return name in chain(*map(name_of_call, calls))
        for callee in funcs_declared_in_current_module.keys():
            for (caller, caller_node) in six.iteritems(self.cythonized_funcs):
                if is_called_in(callee, caller_node):
                    called_funcs.append(callee)
        if len(called_funcs) > 0:
            names = [ast.alias(name, None) for name in called_funcs]
            fromimport = ast.ImportFrom(module=self.py_modname, names=names, level=0)
            imports.append(ast_to_sourcecode(fromimport))

        return imports

    def visit_Call(self, node):
        #print(ast.dump(node))
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            #print('visit_Call, branch 1')
            if node.func.value.id in self.imported_modules:
                self.imported_modules[node.func.value.id][1] = True
        if isinstance(node.func, ast.Name):
            #print('visit_Call, branch 2')
            if node.func.id in self.imported_functions:
                self.imported_functions[node.func.id][2] = True
        return BASE_CLASS.visit_Call(self, node)

    def visit_FunctionDef(self, node):
        #super(CythVisitor, self).visit_FunctionDef(node)
        new_body = []
        cyth_action = None
        for stmt in node.body:
            if is_docstring(stmt):
                #print('found comment_str')
                docstr = stmt.value.s
                cyth_action = self.parse_cyth_markup(docstr, funcdef_node=node)
            else:
                new_body.append(stmt)
        if cyth_action:
            self.cythonized_funcs[node.name] = node
            if cyth_action[0] == 'defines':
                cyth_def = cyth_action[1]
                typedict = cyth_action[2]
                return_type = cyth_action[3]
                #self.decorators(node, 2)
                self.newline(extra=1)
                cyth_funcname = cyth_helpers.get_cyth_name(node.name)
                # TODO: should allow for user specification
                func_prefix = utool.unindent('''
                @cython.boundscheck(False)
                @cython.wraparound(False)
                ''').strip()

                return_string = (" %s " % return_type) if return_type is not None else " "
                self.statement(node, func_prefix + '\ncpdef%s%s(' % (return_string, cyth_funcname,))
                types_minus_sigtypes = self.signature(node.args, typedict=typedict)
                cyth_def_body = self.typedict_to_cythdef(types_minus_sigtypes)
                self.write(')')
                if getattr(node, 'returns', None) is not None:
                    self.write(' ->', node.returns)
                self.write(':')
                self.indentation += 1
                for s in cyth_def_body:
                    self.write('\n', s)
                self.indentation -= 1
                self.body(new_body)
            elif cyth_action[0] == 'replace':
                cyth_def = cyth_action[1]
                self.newline(extra=1)
                self.write(cyth_def)
        else:
            self.plain_funcs[node.name] = node

    def comma_list(self, items, trailing=False):
        for idx, item in enumerate(items):
            if idx:
                self.write(', ')
            self.visit(item)
        if trailing:
            self.write(',')

    def get_benchmarks(self):
        # TODO: let each function individually specify number
        codes = '\n\n\n'.join(self.benchmark_codes)  # NOQA
        list_ = [utool.quasiquote('{func}(iterations)') for func in self.benchmark_names]
        all_benchmarks = utool.indent('\n'.join(list_), '        ').strip()  # NOQA
        py_modname = self.py_modname  # NOQA
        return utool.quasiquote(utool.unindent(
            r"""
            #!/usr/bin/env python
            from __future__ import absolute_import, division, print_function
            import timeit
            import textwrap
            import warnings
            import utool
            warnings.simplefilter('ignore', SyntaxWarning)
            print, print_, printDBG, rrr, profile = utool.inject(__name__, '[{py_modname}.bench]')


            {codes}


            def run_all_benchmarks(iterations):
                print('\n\n')
                print('=======================================')
                print('[cyth] Run benchmarks for: {py_modname}')
                with utool.Indenter(' *  '):
                    {all_benchmarks}

            if __name__ == '__main__':
                run_all_benchmarks(1000)""").strip('\n'))


def is_docstring(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Str)


def assignment_targets(node):
    """
    Assign nodes have a list of multiple targets, which is used for
    'a = b = c' (a and b are both targets)

    'x, y = y, x' has a tuple as the only element of the targets array,
    (likewise for '[x, y] = [y, x]', but with lists)
    """
    assert isinstance(node, (ast.Assign, ast.AugAssign)), type(node)
    if isinstance(node, ast.AugAssign):
        assign_targets = [node.target]
        return assign_targets
    elif isinstance(node, ast.Assign):
        assign_targets = []
        for target in node.targets:
            if isinstance(target, (ast.Tuple, ast.List)):
                assign_targets.extend(target.elts)
            else:
                assign_targets.append(target)
        return assign_targets
    else:
        raise AssertionError('unexpected node type %r' % type(node))


class FirstpassInformationGatherer(ast.NodeVisitor):
    def __init__(self):
        self.global_names = []
    def visit_Module(self, node):
        for subnode in node.body:
            if isinstance(subnode, (ast.Assign, ast.AugAssign)):
                assign_targets = assignment_targets(subnode)
                for target in assign_targets:
                    self.global_names.append(target)


class SecondpassInformationGatherer(ast.NodeVisitor):
    def __init__(self, fpig):
        self.fpig = fpig
        self.globals_used = {name: False for name in fpig.global_names}
    def visit_Name(self, node):
        isname = lambda x: isinstance(x, ast.Name)
        getid = lambda x: x.id
        if getid(node) in map(getid, filter(isname, self.fpig.global_names)) and isinstance(node.ctx, ast.Load):
            self.globals_used[node] = True
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            isattribute = lambda x: isinstance(x, ast.Attribute)
            hasloadctx = lambda x: isinstance(x.value, ast.Name) and isinstance(x.value.ctx, ast.Load)
            filt = lambda x: isattribute(x) and hasloadctx(x)
            gettup = lambda x: (x.value.id, x.attr)
            if gettup(node) in map(gettup, filter(filt, self.fpig.global_names)):
                self.globals_used[node] = True


class CallRecorder(ast.NodeVisitor):
    def __init__(self):
        self.calls = []
    def visit_Call(self, node):
        self.calls.append(node)


def get_funcalls_in_node(node):
    cr = CallRecorder()
    cr.visit(node)
    return cr.calls


def ast_to_sourcecode(node):
    generator = astor.codegen.SourceGenerator(' ' * 4)
    generator.visit(node)
    return ''.join(generator.result)


def replace_funcalls(source, funcname, replacement):
    """
    >>> from cyth_script import *  # NOQA
    >>> replace_funcalls('foo(5)', 'foo', 'bar')
    'bar(5)'
    >>> replace_funcalls('foo(5)', 'bar', 'baz')
    'foo(5)'

    <CYTH>
    </CYTH>
    """

    # FIXME: !!!
    # http://docs.cython.org/src/userguide/wrapping_CPlusPlus.html#nested-class-declarations
    # C++ allows nested class declaration. Class declarations can also be nested in Cython:
    # Note that the nested class is declared with a cppclass but without a cdef.
    class FunctioncallReplacer(ast.NodeTransformer):
        def visit_Call(self, node):
            """CYTH></CYTH>"""
            if isinstance(node.func, ast.Name) and node.func.id == funcname:
                node.func.id = replacement
            return node
    generator = astor.codegen.SourceGenerator(' ' * 4)
    generator.visit(FunctioncallReplacer().visit(ast.parse(source)))
    return ''.join(generator.result)
    #return ast.dump(tree)


def infer_return_type(funcdef_node, typedict):
    class ReturnTypeInferrer(ast.NodeVisitor):
        def __init__(self, node):
            self.return_type = None
            self.visited_returns = []

            assert isinstance(node, ast.FunctionDef), type(node)
            funcdef = node
            self.visit(funcdef)
            #print('visited_returns: %r' % self.visited_returns)
            if utool.list_allsame(self.visited_returns) and len(self.visited_returns) > 0:
                self.return_type = self.visited_returns[0]

        def visit_Return(self, node):
            if node.value:
                if isinstance(node.value, ast.Name):
                    self.visited_returns.append(typedict.get(node.value.id, None))
                elif isinstance(node.value, ast.Tuple):
                    self.visited_returns.append("tuple")

    return ReturnTypeInferrer(funcdef_node).return_type


def parse_doctest_examples(source):
    # parse list of docstrings
    comment_iter = doctest.DocTestParser().parse(source)
    # remove any non-doctests
    example_list = [c for c in comment_iter if isinstance(c, doctest.Example)]
    return example_list


def get_benchline(src, funcname):
    """ Returns the  from a doctest source """
    pt = ast.parse(src)
    assert isinstance(pt, ast.Module), type(pt)
    body = pt.body
    if len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, (ast.Expr, ast.Assign)):
        return None
    if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name):
        if stmt.value.func.id == funcname:
            benchline = ast_to_sourcecode(stmt.value)
            return benchline


def make_benchmarks(funcname, docstring, py_modname):
    r"""
    >>> from cyth.cyth_script import *  # NOQA
    >>> funcname = 'replace_funcalls'
    >>> docstring = replace_funcalls.func_doc
    >>> py_modname = 'cyth.cyth_script'
    >>> benchmark_list = list(make_benchmarks(funcname, docstring, py_modname))
    >>> print(benchmark_list)

    #>>> output = [((x.source, x.want), y.source, y.want) for x, y in benchmark_list]
    #>>> print(utool.hashstr(repr(output)))
    """
    doctest_examples = parse_doctest_examples(docstring)
    test_lines = []
    cyth_lines = []
    setup_lines = []
    cyth_funcname = cyth_helpers.get_cyth_name(funcname)
    for example in doctest_examples:
        benchline = get_benchline(example.source, funcname)
        if benchline is not None:
            test_lines.append(benchline)
            cyth_lines.append(replace_funcalls(benchline, funcname, cyth_funcname))
            setup_lines.append(example.source)
        else:
            setup_lines.append(example.source)
    test_tuples = list(zip(test_lines, cyth_lines))
    setup_script = utool.unindent(''.join(setup_lines))
    #modname = 'vtool.keypoint'
    setup_script = 'from %s import %s\n' % (py_modname, cyth_funcname,) + setup_script
    return test_tuples, setup_script


def parse_benchmarks(funcname, docstring, py_modname):
    test_tuples_, setup_script_ = make_benchmarks(funcname, docstring, py_modname)
    if len(test_tuples_) == 0:
        test_tuples = '[]'
    else:
        test_tuples = '[\n        ' + '\n    '.join(list(map(str, test_tuples_))) + '\n    ]'  # NOQA
    setup_script = utool.indent(setup_script_).strip()  # NOQA
    benchmark_name = utool.quasiquote('run_benchmark_{funcname}')
    #test_tuples, setup_script = make_benchmarks('''{funcname}''', '''{docstring}''')
    # http://en.wikipedia.org/wiki/Relative_change_and_difference
    bench_code = utool.unindent(
        r"""
        def {benchmark_name}(iterations):
            test_tuples = {test_tuples}
            setup_script = textwrap.dedent('''
            {setup_script}
            ''')
            time_line = lambda line: timeit.timeit(stmt=line, setup=setup_script, number=iterations)
            time_pair = lambda (x, y): (time_line(x), time_line(y))
            def print_timing_info(tup):
                from math import log
                print('\n---------------')
                print('[bench] timing {benchmark_name} for %d iterations' % (iterations))
                print('[bench] tests:')
                print('    ' + str(tup))
                (pyth_time, cyth_time) = time_pair(tup)
                print("[bench.python] {funcname} time=%f seconds" % (pyth_time))
                print("[bench.cython] {funcname} time=%f seconds" % (cyth_time))
                time_delta = cyth_time - pyth_time
                pcnt_change_wrt_cyth = (time_delta / pyth_time) * 100
                nepers  = log(cyth_time / pyth_time)
                if time_delta < 0:
                    print('[bench.result] cython was %.1f%% faster' % (-pcnt_change_wrt_cyth,))
                    print('[bench.result] cython was %.1f nepers faster' % (-nepers,))
                    print('[bench.result] cython was faster by %f seconds' % -time_delta)
                else:
                    print('[bench.result] cython was %.1f%% slower' % (pcnt_change_wrt_cyth,))
                    print('[bench.result] cython was %.1f nepers slower' % (nepers,))
                    print('[bench.result] python was faster by %f seconds' % time_delta)
                return (pyth_time, cyth_time)
            return list(map(print_timing_info, test_tuples))""").strip('\n')
    return (benchmark_name, utool.quasiquote(bench_code))


def translate_fpath(py_fpath):
    """ creates a cython pyx file from a python file with cyth tags """
    # Get cython pyx and benchmark output path
    cy_fpath = cyth_helpers.get_cyth_path(py_fpath)
    cy_bpath = cyth_helpers.get_cyth_bench_path(py_fpath)
    # Infer the python module name
    py_modname = cyth_helpers.get_py_module_name(py_fpath)
    # Read the python file
    py_text = utool.read_from(py_fpath, verbose=False)
    # dont parse files without tags
    if py_text.find('<CYTH') == -1:
        return None
    print('[cyth.translate_fpath] py_fpath=%r' % py_fpath)
    # Parse the python file
    visitor = CythVisitor(py_modname=py_modname)
    visitor.visit(ast.parse(py_text))
    # Get the generated pyx file and benchmark file
    cython_text = visitor.get_result()
    bench_text = visitor.get_benchmarks()
    # Write pyx and benchmark
    utool.write_to(cy_fpath, cython_text)
    utool.write_to(cy_bpath, bench_text, verbose=False)
    return cy_bpath


def translate(*paths):
    """ Translates a list of paths """
    cy_bench_list = []
    for fpath in paths:
        if isfile(fpath):
            abspath = utool.unixpath(fpath)
            cy_bench = translate_fpath(abspath)
            if cy_bench is not None:
                cy_bench_list.append(cy_bench)

    if len(cy_bench_list) > 0:
        # write script to run all cyth benchmarks
        cmd_list = ['python ' + bench for bench in cy_bench_list]
        runbench_text = '\n'.join(['#!/bin/bash'] + cmd_list)
        utool.write_to('run_cyth_benchmarks.sh', runbench_text)
        #try:
        import os
        os.chmod('run_cyth_benchmarks.sh', 33277)
        #except OSError:
        #    pass


def translate_all():
    """ Translates a all python paths in directory """
    dpaths = utool.ls_moduledirs('.')
    #print('[cyth] translate_all: %r' % (dpaths,))

    globkw = {
        'recursive': True,
        'with_dirs': False,
        'with_files': True
    }
    # Find all unique python files in directory
    fpaths_iter = [utool.glob(utool.unixpath(dpath), '*.py', **globkw)
                   for dpath in dpaths]
    fpath_iter = utool.iflatten(fpaths_iter)
    abspath_iter = map(utool.unixpath, fpath_iter)
    fpath_list = list(set(list(abspath_iter)))
    #print('[cyth] translate_all: %s' % ('\n'.join(fpath_list),))
    # Try to translate each
    translate(*fpath_list)
    #for fpath in fpath_list:
    #    abspath = utool.unixpath(fpath)
    #    translate_fpath(abspath)


#exec(cyth.import_cyth_execstr(__name__))

if __name__ == '__main__':
    print('[cyth] main')
    input_path_list = utool.get_fpath_args(sys.argv[1:], pat='*.py')
    print(input_path_list)
    print('[cyth] nInput=%d' % (len(input_path_list,)))
    translate(*input_path_list)
