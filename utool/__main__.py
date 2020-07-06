# -*- coding: utf-8 -*-
def main():  # nocover
    import utool

    print('Looks like the imports worked')
    print('utool = {!r}'.format(utool))
    print('utool.__file__ = {!r}'.format(utool.__file__))
    print('utool.__version__ = {!r}'.format(utool.__version__))

    import networkx

    print('networkx = {!r}'.format(networkx))
    print('networkx.__file__ = {!r}'.format(networkx.__file__))
    print('networkx.__version__ = {!r}'.format(networkx.__version__))


if __name__ == '__main__':
    """
    CommandLine:
       python -m utool
    """
    main()
