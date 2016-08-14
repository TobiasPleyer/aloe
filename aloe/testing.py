"""
Utilities for testing libraries using Aloe.
"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
# pylint:disable=redefined-builtin
from builtins import super
# pylint:enable=redefined-builtin

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from functools import wraps

from aloe import world
from aloe.fs import path_to_module_name
from aloe.plugin import GherkinLoader
from aloe.registry import (
    CALLBACK_REGISTRY,
    PriorityClass,
    STEP_REGISTRY,
)
from aloe.runner import GherkinRunner, TestProgram
from aloe.utils import callable_type


@contextmanager
def _in_directory(directory):
    """
    A context manager to run the payload in a specified directory.

    On exit, all modules that were imported from this directory are removed
    from sys.modules.
    """

    directory = os.path.abspath(directory)
    last_wd = os.getcwd()

    os.chdir(directory)

    try:
        yield
    finally:
        os.chdir(last_wd)

        # Unload modules which are loaded from the directory
        unload_modules = []
        unload_path_prefix = os.path.join(directory, '')
        for module_name, module in sys.modules.items():
            # Find out where is the module loaded from
            try:
                path = module.__file__
            except AttributeError:
                # Maybe a namespace package module?
                try:
                    if module.__spec__.origin == 'namespace':
                        # pylint:disable=protected-access
                        path = module.__path__._path[0]
                        # pylint:enable=protected-access
                    else:
                        continue
                except AttributeError:
                    continue

            # Is it loaded from a file in the directory?
            path = os.path.abspath(path)
            if not path.startswith(unload_path_prefix):
                continue

            # Does its name match what would it be if the module was really
            # imported from here? Consider two directories, 'foo' and 'foo/bar'
            # on sys.path, foo/bar/baz.py might have been loaded from either.
            path = path[len(unload_path_prefix):]
            if module_name == path_to_module_name(path):
                unload_modules.append(module_name)

        for module in unload_modules:
            del sys.modules[module]


def in_directory(directory):
    """
    A decorator to change the current directory and add the new one to the
    Python module search path.

    Upon exiting, the directory is changed back, the module search path change
    is reversed and all modules loaded from the directory are removed from
    sys.modules.

    Applies to either a function or an instance of
    TestCase, in which case setUp/tearDown are used.
    """

    def wrapper(func_or_class):
        """
        Wrap a function or a test case class to execute in a different
        directory.
        """

        try:
            is_test_case = issubclass(func_or_class, unittest.TestCase)
        except TypeError:
            is_test_case = False

        if is_test_case:
            # Wrap setUp/tearDown
            old_setup = func_or_class.setUp
            old_teardown = func_or_class.tearDown

            in_directory_cm = [None]

            @wraps(old_setup)
            def setUp(self):
                """Wrap setUp to change to given directory first."""
                in_directory_cm[0] = _in_directory(directory)
                in_directory_cm[0].__enter__()
                old_setup(self)

            @wraps(old_teardown)
            def tearDown(self):
                """Wrap tearDown to restore the original directory."""
                old_teardown(self)
                in_directory_cm[0].__exit__(None, None, None)
                in_directory_cm[0] = None

            func_or_class.setUp = setUp
            func_or_class.tearDown = tearDown

            return func_or_class

        else:
            # Wrap a function
            @wraps(func_or_class)
            def wrapped(*args, **kwargs):
                """
                Execute the function in a different directory.
                """

                with _in_directory(directory):
                    return func_or_class(*args, **kwargs)

            return wrapped

    return wrapper


class TestGherkinLoader(GherkinLoader):
    """
    Gherkin test loader remembering the tests it ran.
    """

    def tests_from_file(self, file_):
        """
        Record which tests were run.
        """

        for scenario in super().tests_from_file(file_):
            yield scenario

        self.tests_run.append(file_)


class TestTestProgram(TestProgram):
    """
    A test test runner to store information about the tests run.

    :param stream: a stream to write the output into (optional)
    """

    gherkin_loader = TestGherkinLoader

    def setup_loader(self):
        """Pass extra options to the test loader."""

        self.testLoader.tests_run = self.tests_run

        super().setup_loader()

    def make_runner(self, *args, **kwargs):
        """Pass the stream to the test runner."""
        return GherkinRunner(*args, **kwargs, stream=self.stream)

    def __init__(self, *args, **kwargs):
        self.tests_run = []
        self.stream = kwargs.pop('stream')
        if self.stream:
            kwargs['buffer'] = True

        kwargs['testRunner'] = callable_type(self.make_runner)

        super().__init__(*args, **kwargs)


class FeatureTest(unittest.TestCase):
    """
    Base class for tests running Gherkin features.
    """

    def run_feature_string(self, feature_string):
        """
        Run the specified string as a feature.

        The feature will be created as a temporary file in the 'features'
        directory relative to the current directory. This ensures the steps
        contained within would be found by the loader.
        """

        if not os.path.isdir('features'):
            raise ValueError(
                "Features directory not found in {0}".format(os.getcwd()))

        with tempfile.NamedTemporaryFile(suffix='.feature', dir='features') \
                as feature_file:
            feature_file.write(feature_string.encode('utf-8'))
            feature_file.flush()
            return self.run_features(os.path.relpath(feature_file.name))

    def run_features(self, *features, **kwargs):
        """
        Run the specified features.
        """

        # named keyword args and variable positional args aren't supported on
        # Python 2
        verbosity = kwargs.get('verbosity')
        stream = kwargs.get('stream')
        force_color = kwargs.get('force_color', False)

        # Reset the state of callbacks and steps so that individual tests don't
        # affect each other
        CALLBACK_REGISTRY.clear(priority_class=PriorityClass.USER)
        STEP_REGISTRY.clear()
        world.__dict__.clear()

        argv = ['aloe']

        if verbosity:
            argv += ['--verbosity', str(verbosity)]

        if force_color:
            argv += ['--color']

        argv += list(features)

        # Save the loaded module list to restore later
        old_modules = set(sys.modules.keys())

        result = TestTestProgram(
            module=None,
            exit=False,
            argv=argv,
            stream=stream,
        )

        # To avoid affecting the (outer) testsuite and its subsequent tests,
        # unload all modules that were newly loaded. This also ensures that they
        # are loaded again for the next tests, registering relevant steps and
        # hooks.
        new_modules = set(sys.modules.keys())
        for module_name in new_modules - old_modules:
            del sys.modules[module_name]

        return result

    def assert_feature_success(self, *features, **kwargs):
        """
        Assert that the specified features can be run successfully.
        """

        result = self.run_features(*features, **kwargs)
        assert result.result.wasSuccessful()
        return result

    def assert_feature_fail(self, *features, **kwargs):
        """
        Assert that the specified features fail when run.
        """

        result = self.run_features(*features, **kwargs)
        assert not result.result.wasSuccessful()
        return result
