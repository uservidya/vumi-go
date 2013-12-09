import requests

from hashlib import md5
from urlparse import urljoin

from go.vouchers import settings


class AirtimeVoucherServiceError(Exception):
    """Raised when an error occurs with the Airtime Voucher service"""


class AirtimeVoucherService(object):
    """Airtime Voucher Service proxy"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls._instance, cls):
            cls._instance = object.__new__(cls, *args, **kwargs)
        return cls._instance

    def import_vouchers(self, pool_name, content):
        """Import the vouchers `content` into the given `pool_name`"""
        url = urljoin(settings.AIRTIME_VOUCHER_SERVICE_URL,
                      '%s/import/req-0' % (pool_name,))

        content_md5 = md5(content).hexdigest().lower()
        headers = {'Content-MD5': content_md5}
        response = requests.put(url, content, headers=headers)
        if response.status_code not in [200, 201]:
            raise AirtimeVoucherServiceError(response.text)
