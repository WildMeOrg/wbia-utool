# -*- coding: utf-8 -*-
def main():  # nocover
    import vtool

    print('Looks like the imports worked')
    print('vtool = {!r}'.format(vtool))
    print('vtool.__file__ = {!r}'.format(vtool.__file__))
    print('vtool.__version__ = {!r}'.format(vtool.__version__))

    import networkx

    print('networkx = {!r}'.format(networkx))
    print('networkx.__file__ = {!r}'.format(networkx.__file__))
    print('networkx.__version__ = {!r}'.format(networkx.__version__))


if __name__ == '__main__':
    """
    CommandLine:
       python -m vtool
    """
    main()
