# -*- coding: utf-8 -*-
"""
Utilities for IPython/Jupyter Notebooks


CommandLine:
    # to connect to a notebook on a remote machine that does not have the
    # appropriate port exposed you must start an SSH tunnel.
    # Typically a jupyter-notebook runs on port 8888.
    # Run this command on your local machine.
    ssh -N -f -L localhost:8888:localhost:8889 <remote_user>@<remote_host>
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import sys
from utool import util_inject
from collections import namedtuple
print, rrr, profile = util_inject.inject2(__name__)


IPYNBCell = namedtuple('IPYNBCell', ['header', 'code', 'footer'])


def make_autogen_str():
    r"""
    Returns:
        str:

    CommandLine:
        python -m utool.util_ipynb --exec-make_autogen_str --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from utool.util_ipynb import *  # NOQA
        >>> import utool as ut
        >>> result = make_autogen_str()
        >>> print(result)
    """
    import utool as ut
    def get_regen_cmd():
        try:
            if len(sys.argv) > 0 and ut.checkpath(sys.argv[0]):
                # Check if running python command
                if ut.is_python_module(sys.argv[0]):
                    python_exe = ut.python_executable(check=False)
                    modname = ut.get_modname_from_modpath(sys.argv[0])
                    new_argv = [python_exe, '-m', modname] + sys.argv[1:]
                    return ' '.join(new_argv)
        except Exception as ex:
            ut.printex(ex, iswarning=True)
        return ' '.join(sys.argv)

    autogenkw = dict(
        stamp=ut.timestamp('printable'),
        regen_cmd=get_regen_cmd()
        #' '.join(sys.argv)
    )
    return ut.codeblock(
        '''
        # Autogenerated on {stamp}
        # Regen Command:
        #    {regen_cmd}
        #
        '''
    ).format(**autogenkw)


def export_notebook(run_nb, fname):
    import IPython.nbconvert.exporters
    import codecs
    #exporter = IPython.nbconvert.exporters.PDFExporter()
    exporter = IPython.nbconvert.exporters.HTMLExporter()
    output, resources = exporter.from_notebook_node(run_nb)
    ext = resources['output_extension']
    output_fpath = fname + ext
    #codecs.open(output_fname, 'w', encoding='utf-8').write(output)
    codecs.open(output_fpath, 'w').write(output)
    return output_fpath
    #IPython.nbconvert.exporters.export_python(runner.nb)


def run_ipython_notebook(notebook_str):
    """
    References:
        https://github.com/paulgb/runipy
        >>> from utool.util_ipynb import *  # NOQA
    """
    from runipy.notebook_runner import NotebookRunner
    import nbformat
    import logging
    log_format = '%(asctime)s %(levelname)s: %(message)s'
    log_datefmt = '%m/%d/%Y %I:%M:%S %p'
    logging.basicConfig(
        level=logging.INFO, format=log_format, datefmt=log_datefmt
    )
    #fpath = 'tmp.ipynb'
    #notebook_str = ut.readfrom(fpath)
    #nb3 = IPython.nbformat.reads(notebook_str, 3)
    #cell = nb4.cells[1]
    #self = runner
    #runner = NotebookRunner(nb3, mpl_inline=True)
    print('Executing IPython notebook')
    nb4 = nbformat.reads(notebook_str, 4)
    runner = NotebookRunner(nb4)
    runner.run_notebook(skip_exceptions=False)
    run_nb = runner.nb
    return run_nb


def normalize_cells(block):
    if isinstance(block, (tuple, list)):
        if len(block) == 2:
            header, code = block
            footer = None
        elif len(block) == 3:
            header, code, footer = block
        else:
            assert False
    else:
        header = None
        footer = None
        code = block
    return IPYNBCell(header, code, footer)


def format_cells(block, locals_=None):
    import utool as ut
    try:
        if isinstance(block, (tuple, list)):
            if len(block) == 2:
                header, code = block
                footer = None
            elif len(block) == 3:
                header, code, footer = block
            else:
                assert False
        else:
            header = None
            footer = None
            code = block

        if header is not None:
            replace_chars = [('’', '\''), ('–', '-')]  # NOQA
            for tup in replace_chars:
                header = header.replace(*tup)

        if footer is not None:
            replace_chars = [('’', '\''), ('–', '-')]  # NOQA
            for tup in replace_chars:
                footer = footer.replace(*tup)

        if locals_ is not None and code is not None:

            def modify_code_indent_formatdict(code, locals_):
                # Parse out search and replace locations in code
                ncl1 = ut.negative_lookbehind('{')
                ncl2 = ut.negative_lookahead('{')
                ncr1 = ut.negative_lookbehind('}')
                ncr2 = ut.negative_lookahead('}')
                left = ncl1 + '{' + ncl2
                right = ncr1 + '}' + ncr2
                fmtpat = left + ut.named_field('key', '[^}]*') + right
                spacepat = ut.named_field('indent', '^\s+')
                pattern = spacepat + fmtpat
                import re
                seen_ = set([])
                for m in re.finditer(pattern, code, flags=re.MULTILINE):
                    indent = (m.groupdict()['indent'])
                    key = (m.groupdict()['key'])
                    if key in locals_ and key not in seen_:
                        seen_.add(key)
                        locals_[key] = ut.indent_rest(locals_[key], indent)

            modify_code_indent_formatdict(code, locals_)
            code_ = code.format(**locals_)
            ut.is_valid_python(code_, reraise=True, ipy_magic_workaround=True)
        else:
            code_ = code
        cell_list = []
        if header is not None:
            cell_list += [markdown_cell(header)]
        if code is not None:
            cell_list += [code_cell(code_)]
        if footer is not None:
            cell_list += [markdown_cell(footer)]
        return cell_list
    except Exception as ex:
        ut.printex(ex, 'failed to format cell', keys=['header', 'block'])
        raise


def code_cell(sourcecode):
    r"""
    Args:
        sourcecode (str):

    Returns:
        str: json formatted ipython notebook code cell

    CommandLine:
        python -m wbia.templates.generate_notebook --exec-code_cell

    Example:
        >>> # DISABLE_DOCTEST
        >>> from wbia.templates.generate_notebook import *  # NOQA
        >>> sourcecode = notebook_cells.timestamp_distribution[1]
        >>> sourcecode = notebook_cells.initialize[1]
        >>> result = code_cell(sourcecode)
        >>> print(result)
    """
    import utool as ut
    sourcecode = ut.remove_codeblock_syntax_sentinals(sourcecode)
    cell_header = ut.codeblock(
        '''
        {
         "cell_type": "code",
         "execution_count": null,
         "metadata": {
          "collapsed": true
         },
         "outputs": [],
         "source":
        ''')
    cell_footer = ut.codeblock(
        '''
        }
        ''')
    if sourcecode is None:
        source_line_repr = ' []\n'
    else:
        lines = sourcecode.split('\n')
        line_list = [line + '\n' if count < len(lines) else line
                     for count, line in enumerate(lines, start=1)]
        #repr_line_list = [repr_single_for_md(line) for line in line_list]
        repr_line_list = [repr_single_for_md(line) for line in line_list]
        source_line_repr = ut.indent(',\n'.join(repr_line_list), ' ' * 2)
        source_line_repr = ' [\n' + source_line_repr + '\n ]\n'
    return (cell_header + source_line_repr + cell_footer)


def markdown_cell(markdown):
    r"""
    Args:
        markdown (str):

    Returns:
        str: json formatted ipython notebook markdown cell

    CommandLine:
        python -m wbia.templates.generate_notebook --exec-markdown_cell

    Example:
        >>> # DISABLE_DOCTEST
        >>> from wbia.templates.generate_notebook import *  # NOQA
        >>> markdown = '# Title'
        >>> result = markdown_cell(markdown)
        >>> print(result)
    """
    import utool as ut
    markdown_header = ut.codeblock(
        '''
          {
           "cell_type": "markdown",
           "metadata": {},
           "source": [
        '''
    )
    markdown_footer = ut.codeblock(
        '''
           ]
          }
        '''
    )
    return (markdown_header + '\n' +
            ut.indent(repr_single_for_md(markdown), ' ' * 2) +
            '\n' + markdown_footer)


def make_notebook(cell_list):
    """
    References:
        # Change cell width
        http://stackoverflow.com/questions/21971449/how-do-i-increase-the-cell-width-of-the-ipython-notebook-in-my-browser/24207353#24207353
    """
    import utool as ut
    header = ut.codeblock(
        '''
        {
         "cells": [
        '''
    )

    footer = ut.codeblock(
        '''
         ],
         "metadata": {
          "kernelspec": {
           "display_name": "Python 2",
           "language": "python",
           "name": "python2"
          },
          "language_info": {
           "codemirror_mode": {
            "name": "ipython",
            "version": 2
           },
           "file_extension": ".py",
           "mimetype": "text/x-python",
           "name": "python",
           "nbconvert_exporter": "python",
           "pygments_lexer": "ipython2",
           "version": "2.7.6"
          }
         },
         "nbformat": 4,
         "nbformat_minor": 0
        }
        ''')

    cell_body = ut.indent(',\n'.join(cell_list), '  ')
    notebook_str = header + '\n' + cell_body +  '\n' +  footer
    try:
        import json
        json.loads(notebook_str)
    except ValueError as ex:
        ut.printex(ex, 'Invalid notebook JSON')
        raise
    return notebook_str


def repr_single_for_md(s):
    r"""
    Args:
        s (str):

    Returns:
        str: str_repr

    CommandLine:
        python -m wbia.templates.generate_notebook --exec-repr_single_for_md --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from wbia.templates.generate_notebook import *  # NOQA
        >>> s = '#HTML(\'<iframe src="%s" width=700 height=350></iframe>\' % pdf_fpath)'
        >>> result = repr_single_for_md(s)
        >>> print(result)
    """
    import utool as ut
    if True:
        str_repr = ut.reprfunc(s)
        import re
        if str_repr.startswith('\''):
            dq = (ut.DOUBLE_QUOTE)
            sq = (ut.SINGLE_QUOTE)
            bs = (ut.BACKSLASH)
            dq_, sq_, bs_ = list(map(re.escape, [dq, sq, bs]))
            no_bs = ut.negative_lookbehind(bs_)
            #no_sq = ut.negative_lookbehind(sq)
            #no_dq = ut.negative_lookbehind(dq)

            #inside = str_repr[1:-1]
            #inside = re.sub(no_bs + dq, bs + dq, inside)
            #inside = re.sub(no_bs + bs + sq, r"\\'", r"'", inside)
            #str_repr = '"' + inside + '"'
            #inside = re.sub(r'"', r'\\"', inside)
            #inside = re.sub(ut.negative_lookbehind(r"'") + r"\\'", r"'", inside)

            inside = str_repr[1:-1]
            # Escape double quotes
            inside = re.sub(no_bs + r'"', r'\\"', inside)
            # Unescape single quotes
            inside = re.sub(no_bs + bs_ + r"'", r"'", inside)
            # Append external double quotes
            str_repr = '"' + inside + '"'
        return str_repr
    else:
        return '"' + ut.reprfunc('\'' + s)[2:]


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m utool.util_ipynb
        python -m utool.util_ipynb --allexamples
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
