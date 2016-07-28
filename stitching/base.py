"""
This module contains code for setting up visual regression test cases.

A visual regression test is one that checks the rendered state of an element
against a known working baseline image.

E.g.

Test case

.. code:: python

    class FooTestCase(SeleniumRegressionTestCase):
        _CONFIG_FILE = 'test.ini'
        _APP_CONFIG_SECTION = 'appname'

        @classmethod
        def build_app(cls, settings):
        \"""
        Return an instance of a wsgi application.

        :param dict settings: A dictionary containing application specific
            settings.
        :return: WSGI application.
        \"""
        from myapp import main
        return main(settings)

        def test_url(self):
            self.assertScreenshot('.foo_class', '/url')


The above will launch the application and connect to the selenium server running
on the vagrant box. The assertScreenshot will retrieve a screen shot of the
passed element on the page and compare it with the baseline image. Any
differences will cause an exception to be raised.

Relevant selenium config:

.. code:: ini

    [selenium]
    command_executor = http://127.0.0.1:4444/wd/hub
    base_url = http://192.168.33.1:5009
    display_keys = xs
    browser_keys = chrome_mobile
    make_baseline_screenshots = false
    screenshot_dir = /tmp/screenshots

    [selenium:display_xs]
    width = 767
    height = 1022
    pixel_ratio = 3

    [selenium:browser_chrome_mobile]
    options_module = selenium.webdriver.chrome.options
    arguments = --disable-extensions
    mobile = false

Config sections:
* selenium
  * commend_executor - This is the IP address of the virtual box that is running
    the selenium server.
  * base_url - The application host. This IP should be accessible by the
    selenium server.
  * display_keys - Each key references a display_{key} section of the config.
    Only display sections with their keys here will be tested against.
  * browser_keys - Each key references a browser_{key} section of the config.
    Only browser sections with their keys here will be tested against.
  * make_baseline_screenshots - Boolean indicating if the tests should be run
    to generate baseline screenshots. No assertions happen if this is set to
    true.
  * screenshot_dir - Directory where baseline screenshots will be
    saved/loaded to/from.

* selenium:display_{key}
  * width - Pixel width to set the browser to before taking the screenshot.
  * height - Pixel height to set the browser to before taking the screenshot.
  * pixel_ratio - Display ratio to set the browser to before taking the
    screenshot.

* selenium:browser_{key}
  * options_module - Python module to load related Options class from.
  * arguments - Newline seperated list of command line arguments to pass to the
    browser
  * mobile - Boolean indicating if the browser should emulate a mobile device.

"""
from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import os
import unittest
from ConfigParser import SafeConfigParser
from importlib import import_module
from itertools import product
from time import sleep

from PIL import Image
from needle.driver import NeedleRemote
from needle.engines.pil_engine import ImageDiff
from paste.deploy.converters import asbool, aslist
from selenium.webdriver.remote.remote_connection import LOGGER

from stitching.exceptions import AssertScreenshotException, InvalidBrowserException, MissingBaselineScreenshotException

LOGGER.setLevel(logging.WARNING)
log = logging.getLogger(__name__)


class SeleniumRegressionTestCase(unittest.TestCase):
    _APP_CONFIG_SECTION = 'myapp'
    _BASELINE_FOLDER_NAME = 'baseline'
    _ERROR_FOLDER_NAME = 'errors'
    _CONFIG_FILE = 'example.ini'
    _SELENIUM_CONFIG_BROWSER_PREFIX = 'browser_'
    _SELENIUM_CONFIG_DISPLAY_PREFIX = 'display_'
    _SELENIUM_CONFIG_SECTION = 'selenium'
    _THRESHOLD = 0

    @classmethod
    def setUpClass(cls):
        """
        Load config files.

        Use :func:`SeleniumRegressionTestCase._parse_selenium_config` to parse and store values found in the config
        file that is specified by the `_CONFIG_FILE` class member.
        """
        cwd = os.getcwd()
        config = SafeConfigParser()
        config.read('{}/{}'.format(
            cwd,
            cls._CONFIG_FILE))

        cls._selenium_settings = cls._parse_selenium_config(config)

    def assertScreenshot(self, selector, path):
        """
        Assert that the element as defined by the passed CSS `selector` is
        the same as the one saved in the baseline screenshot.

        Note that this method will generate a baseline screenshot if the
        make_baseline_screenshots config option is set to true. No assertions
        will occur.

        :param unicode selector: CSS selector of element to screenshot.
        :param path: URL path to page where element is found.
        """
        for display_name, browser_name, driver in self._yield_drivers():
            url = self._make_url(path)
            driver.get(url)

            # selenium checks for a str instance. Unicode would fail here.
            element = driver.find_element_by_css_selector(str(selector))
            sleep(1)
            screenshot = element.get_screenshot()

            baseline_path = self._make_screenshot_path(
                self._BASELINE_FOLDER_NAME,
                browser_name,
                display_name)

            baseline_file = '{}/{}--{}.png'.format(
                baseline_path,
                path,
                selector)
            # Create the directory if it does not exist.
            if not os.path.exists(baseline_path):
                os.makedirs(baseline_path)

            if self._make_baseline_screenshots:
                screenshot.save(baseline_file)
                log.warning('Creating baseline screenshot: {}'.format(
                    baseline_file))
            else:
                try:
                    baseline_screenshot = Image.open(baseline_file).convert('RGB')
                except IOError:
                    raise MissingBaselineScreenshotException

                error_path = self._make_screenshot_path(
                    self._ERROR_FOLDER_NAME,
                    browser_name,
                    display_name)

                if not os.path.exists(error_path):
                    os.makedirs(error_path)

                error_file = '{}/{}--{}.png'.format(
                    error_path,
                    path,
                    selector)
                try:
                    diff = ImageDiff(screenshot, baseline_screenshot)
                except AssertionError:
                    screenshot.save(error_file)
                    raise AssertScreenshotException(error_file)

                distance = abs(diff.get_distance())
                if distance > self._THRESHOLD:
                    screenshot.save(error_file)
                    raise AssertScreenshotException(distance)
            driver.close()

    @staticmethod
    def _make_chrome_options(browser_settings, display):
        """
        Return a web driver options object that is used to insantiate the
        remote chrome driver.

        :parm dict browser_settings: A dict with key/value pairs extracted from
            the relevant browser config section.
        :param dict display: A dict wit hthe key/value pairs extracted from the
            relevant display config section.
        :return: Selnium options object.
        """
        options = import_module(browser_settings['options_module']).Options()
        for argument in browser_settings['arguments']:
            options.add_argument(argument)

        if browser_settings['mobile']:
            options.add_experimental_option(
                'mobileEmulation',
                {'deviceMetrics': {'width': display['width'],
                                   'height': display['height'],
                                   'pixelRatio': display['pixel_ratio']}})
        return options

    @classmethod
    def _parse_selenium_config(cls, config):
        """
        Parse and convert the selenium sections of the config file and store
        the values in class variables.

        :param config: Config object.
        :type config: A SafeConfigParser instance.
        """
        cls._command_executor = config.get(
            cls._SELENIUM_CONFIG_SECTION, 'command_executor')
        cls._base_url = config.get(
            cls._SELENIUM_CONFIG_SECTION, 'base_url')
        cls._screenshot_dir = config.get(
            cls._SELENIUM_CONFIG_SECTION,
            'screenshot_dir')

        display_keys = aslist(
            config.get(cls._SELENIUM_CONFIG_SECTION,
                       'display_keys'))
        browser_keys = aslist(
            config.get(cls._SELENIUM_CONFIG_SECTION,
                       'browser_keys'))

        cls._make_baseline_screenshots = asbool(
            config.get(cls._SELENIUM_CONFIG_SECTION,
                       'make_baseline_screenshots'))

        cls._make_browers(browser_keys, config)
        cls._make_displays(display_keys, config)

    @classmethod
    def _make_browers(cls, browser_keys, config):
        cls._browsers = {}
        for browser_key in browser_keys:
            section_name = '{}:{}{}'.format(
                cls._SELENIUM_CONFIG_SECTION,
                cls._SELENIUM_CONFIG_BROWSER_PREFIX,
                browser_key)

            section_dict = dict(config.items(section_name))
            section_dict['arguments'] = aslist(section_dict['arguments'])
            section_dict['mobile'] = asbool(section_dict['mobile'])
            cls._browsers[browser_key] = section_dict

    @classmethod
    def _make_displays(cls, display_keys, config):
        cls._displays = {}
        for display_key in display_keys:
            section_name = '{}:{}{}'.format(
                cls._SELENIUM_CONFIG_SECTION,
                cls._SELENIUM_CONFIG_DISPLAY_PREFIX,
                display_key)

            section_dict = dict(config.items(section_name))
            section_dict['width'] = int(section_dict['width'])
            section_dict['height'] = int(section_dict['height'])
            section_dict['pixel_ratio'] = float(section_dict['pixel_ratio'])
            cls._displays[display_key] = section_dict

    def _make_url(self, path):
        """
        Return a concatenation of the app_host value found in the config file
        and supplied path.
        """
        return '{}/{}'.format(self._base_url, path)

    def _make_screenshot_path(self, folder, browser_name, display_name):
        """
        Generate a unicode path to be used for saving a screenshot.

        :param unicode folder: The name of the folder to save to.
        :param unicode browser_name: The name of the browser in which the screenshot was taken in.
        :param unicode display_name: The name of the display in which the screenshot was taken in.
        :return: Path to directory to save the screen shot under.
        :rtype: Unicode
        """
        return '/'.join((
            self._screenshot_dir,
            folder,
            browser_name,
            display_name
        ))

    def _yield_drivers(self):
        """
        Yield a driver.

        This will yield one web driver for each combination of display and
        browser config section.
        """
        displays_browsers = product(
            self._displays.iteritems(),
            self._browsers.iteritems())

        for display, browser in displays_browsers:
            display_name = display[0]
            display_settings = display[1]
            browser_name = browser[0]
            browser_settings = browser[1]

            if browser_name in ('chrome', 'chrome_mobile'):
                options = self._make_chrome_options(
                    browser_settings, display_settings)
            else:
                raise InvalidBrowserException(browser_name)

            driver = NeedleRemote(
                command_executor=self._command_executor,
                desired_capabilities=options.to_capabilities())

            if not browser_settings['mobile']:
                driver.set_window_size(
                    display_settings['width'],
                    display_settings['height'])
            else:
                driver.maximize_window()

            yield display_name, browser_name, driver

    def test_demo(self):
        self.assertScreenshot('#lst-ib', '/')
