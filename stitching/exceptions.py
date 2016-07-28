class InvalidBrowserException(Exception):
    def __init__(self, browser_name):
        msg = '{} is not supported by the RegressionTestCase class.'.format(
            browser_name)
        super(InvalidBrowserException, self).__init__(msg)


class AssertScreenshotException(AssertionError):
    def __init__(self, distance):
        msg = ('The new screenshot did not match the baseline (by a distance ' +
               'of {})').format(distance)
        super(AssertScreenshotException, self).__init__(msg)


class MissingBaselineScreenshotException(Exception):
    def __init__(self):
        msg = ('Missing baseline screenshots. Please run tests with the ' +
               'make_baseline_screenshots config directive set to true')
        super(MissingBaselineScreenshotException, self).__init__(msg)
