===================
Wildbook IA - utool
===================

|Build| |Pypi| |ReadTheDocs|

Useful Utility Tools For You! - Part of the WildMe / Wildbook IA Project.

Notice: This is a "kitchen sink" library. While it is still somewhat maintained, it should be considered "end-of-life". Please see https://github.com/Erotemic/ubelt and https://github.com/Erotemic/xdevfor a well-maintained curated collection of utilities.

----

The `utool` library is a collection of tools that I've found useful. I've
written most of them from scratch, but there are a few I've taken or partially
taken from StackOverflow. References are given in most locations.

In my experience the most useful functions in this library are:

* `utool.flatten`
* `utool.take`
* `utool.take_column`
* `utool.compress`
* `utool.ichunks`
* `utool.itertwo`
* `utool.isiterable`
* `utool.group_items`
* `utool.dict_subset`
* `utool.dict_hist`
* `utool.map_dict_vals`
* `utool.map_dict_keys`
* `utool.memoize`
* `utool.get_argflag`
* `utool.get_argval`
* `utool.ProgIter`
* `utool.Timer`
* `utool.Timerit`
* `utool.MemoryTracker`
* `utool.InteractiveIter`
* `utool.color_print`
* `utool.ensuredir`
* `utool.glob`
* `utool.grep`
* `utool.sed`
* `utool.ls`
* `utool.repr2`


Installation
--------------
Installation can now be done via pypi

.. code:: bash

    pip install wbia-utool


.. |Build| image:: https://img.shields.io/github/workflow/status/WildbookOrg/wbia-utool/Build%20and%20upload%20to%20PyPI/master
    :target: https://github.com/WildbookOrg/wbia-utool/actions?query=branch%3Amaster+workflow%3A%22Build+and+upload+to+PyPI%22
    :alt: Build and upload to PyPI (master)

.. |Pypi| image:: https://img.shields.io/pypi/v/wbia-utool.svg
   :target: https://pypi.python.org/pypi/wbia-utool
   :alt: Latest PyPI version

.. |ReadTheDocs| image:: https://readthedocs.org/projects/wbia-utool/badge/?version=latest
    :target: http://wbia-utool.readthedocs.io/en/latest/
    :alt: Documentation on ReadTheDocs
