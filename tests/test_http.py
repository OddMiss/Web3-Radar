from __future__ import annotations

import unittest

from web3_radar.http import HttpClient


class HttpClientTests(unittest.TestCase):
    def test_safe_url_redacts_query_and_telegram_token(self) -> None:
        safe = HttpClient._safe_url(
            "https://api.telegram.org/bot123456:SECRET/sendMessage?signature=private"
        )
        self.assertEqual(safe, "https://api.telegram.org/bot***/sendMessage")
        self.assertNotIn("SECRET", safe)
        self.assertNotIn("signature", safe)


if __name__ == "__main__":
    unittest.main()
