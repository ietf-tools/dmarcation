from copy import deepcopy
from unittest.mock import patch

import src.milter.processor


class TestCheckRequiredHeaders:
    """
    Test the `check_required_headers()` function
    """

    def test_is_true_if_not_required(self):
        """
        If there is no `header` entry in the required configuration then
        check_required_headers should return true.
        """
        config = {}

        assert src.milter.processor.check_required_headers(config, [])

    def test_header_must_be_present(self):
        """
        If the header entry is set true then the header simply needs to exist
        for the code to return true.
        """
        config = {"header": {"X-Some-Header": True}}

        headers = [
            {
                "name": "X-Some-Header",
                "lower_name": "x-some-header",
                "value": " Some Value",
            }
        ]

        assert src.milter.processor.check_required_headers(config, []) is False
        assert src.milter.processor.check_required_headers(config, headers)

    def test_header_must_have_specific_value(self):
        """
        If the header entry is a string then it must match completely.
        """
        config = {"header": {"X-Some-Header": "A Value"}}

        headers = [
            {
                "name": "X-Some-Header",
                "lower_name": "x-some-header",
                "value": " Some Value",
            }
        ]

        assert src.milter.processor.check_required_headers(config, headers) is False

        config["header"]["X-Some-Header"] = "Some Value"
        assert src.milter.processor.check_required_headers(config, headers)

    def test_header_has_list_value(self):
        """
        If the header entry is a list then one value must match completely
        """
        config = {"header": {"X-Some-Header": ["A Value"]}}

        headers = [
            {
                "name": "X-Some-Header",
                "lower_name": "x-some-header",
                "value": " Some Value",
            }
        ]

        assert src.milter.processor.check_required_headers(config, headers) is False

        config["header"]["X-Some-Header"].append("Some Value")
        assert src.milter.processor.check_required_headers(config, headers)


allow_dmarc_record = {
    "location": "example.com",
    "parsed": {"tags": {"p": {"value": "none"}, "sp": {"value": "none"}}},
}

reject_dmarc_record = {
    "location": "example.com",
    "parsed": {"tags": {"p": {"value": "reject"}, "sp": {"value": "quarantine"}}},
}


class TestDmarcChecks:
    """
    Test the code that checks if we need to make modifications in order
    to avoid issues with DMARC.
    """

    @patch.object(
        src.milter.processor.dmarc, "get_dmarc_record", return_value=allow_dmarc_record
    )
    def test_domain_not_in_reject_list(self, _dmarc):
        """
        A domain without a reject/quarantine policy should indicate acceptance.
        """
        assert src.milter.processor.check_dmarc_rejection("example.com") is False

    @patch.object(
        src.milter.processor.dmarc, "get_dmarc_record", return_value=reject_dmarc_record
    )
    def test_domain_in_reject_list(self, _dmarc):
        """
        A domain with a reject/quarantine policy should indicate rejection.
        """
        assert src.milter.processor.check_dmarc_rejection("example.com")

    @patch.object(
        src.milter.processor.dmarc, "get_dmarc_record", return_value=allow_dmarc_record
    )
    def test_subdomain_not_in_reject_list(self, _dmarc):
        """
        A subdomain without a reject/quarantine policy should indicate acceptance.
        """
        assert (
            src.milter.processor.check_dmarc_rejection("somewhere.example.com") is False
        )

    @patch.object(
        src.milter.processor.dmarc, "get_dmarc_record", return_value=reject_dmarc_record
    )
    def test_subdomain_in_reject_list(self, _dmarc):
        """
        A subdomain with a reject/quarantine policy should indicate rejection.
        """
        assert src.milter.processor.check_dmarc_rejection("somewhere.example.com")

    @patch.object(
        src.milter.processor.dmarc,
        "get_dmarc_record",
        side_effect=src.milter.processor.dmarc.DMARCError("foo"),
    )
    def test_errors_are_ignored(self, _dmarc):
        """
        An error looking up the DMARC record should be treated as not rejecting.
        """
        assert src.milter.processor.check_dmarc_rejection("example.com") is False

    def test_all_rejections(self):
        """
        When testing multiple domains all need to reject or it will be considered
        acceptable.
        """
        with patch.object(
            src.milter.processor.dmarc,
            "get_dmarc_record",
            return_value=allow_dmarc_record,
        ):
            assert (
                src.milter.processor.check_all_dmarc_rejections(
                    ["example.com", "somewhere.example.com"]
                )
                is False
            )

        with patch.object(
            src.milter.processor.dmarc,
            "get_dmarc_record",
            return_value=reject_dmarc_record,
        ):
            assert src.milter.processor.check_all_dmarc_rejections(
                ["example.com", "somewhere.example.com"]
            )

        mixed_dmarc_record = deepcopy(allow_dmarc_record)
        mixed_dmarc_record["parsed"]["tags"]["p"]["value"] = "quarantine"
        with patch.object(
            src.milter.processor.dmarc,
            "get_dmarc_record",
            return_value=mixed_dmarc_record,
        ):
            assert (
                src.milter.processor.check_all_dmarc_rejections(
                    ["example.com", "somewhere.example.com"]
                )
                is False
            )


class TestAddressHandling:
    """
    Tests the code that manipulates email addresses.
    """

    def test_address_is_rewritten(self):
        """
        Tests that the address is rewritten correctly.
        """
        result = src.milter.processor.rewrite_email_address(
            ("Some One", "someone@example.com"), "dmarc.example.com"
        )
        assert result == "Some One <someone=40example.com@dmarc.example.com>"

    def test_address_is_rewritten_with_alt_quote(self):
        """
        Tests that the address is rewritten correctly with an alternative quote.
        """
        result = src.milter.processor.rewrite_email_address(
            ("Some One", "someone@example.com"), "dmarc.example.com", "~"
        )
        assert result == "Some One <someone~40example.com@dmarc.example.com>"

    def test_address_quoting(self):
        """
        Tests that the address is quoted correctly.
        """
        result = src.milter.processor.quote_email_address("someone@example.com")
        assert result == "someone=40example.com"

    def test_address_quoting_with_alt_quote(self):
        """
        Tests that the address is quoted correctly with an alternative quote.
        """
        result = src.milter.processor.quote_email_address("someone@example.com", "~")
        assert result == "someone~40example.com"

    def test_address_rewriting_is_reversed(self):
        """
        Tests that the address rewriting is reversed correctly.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone=40example.com@dmarc.example.com")
        )
        assert result == "Some One <someone@example.com>"

    def test_address_rewriting_with_alt_quote_is_reversed(self):
        """
        Tests that the address rewriting is reversed correctly with an alternative quote.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone~40example.com@dmarc.example.com"), None, "~"
        )
        assert result == "Some One <someone@example.com>"

    def test_address_rewriting_with_correct_domain_is_reversed(self):
        """
        Tests that the address rewriting is reversed correctly if the matching
        domain is provided.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone=40example.com@dmarc.example.com"),
            "dmarc.example.com"
        )
        assert result == "Some One <someone@example.com>"

    def test_address_rewriting_with_alt_quote_and_correct_domain_is_reversed(self):
        """
        Tests that the address rewriting is reversed correctly with an alternative quote
        if the matching domain is provided.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone~40example.com@dmarc.example.com"),
            "dmarc.example.com",
            "~"
        )
        assert result == "Some One <someone@example.com>"

    def test_address_rewriting_with_incorrect_domain_is_not_reversed(self):
        """
        Tests that the address rewriting is not reversed if the domain does not match.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone=40example.com@dmarc.example.com"),
            "example.com"
        )
        assert result == "Some One <someone=40example.com@dmarc.example.com>"

    def test_address_rewriting_with_alt_quote_and_incorrect_domain_is_not_reversed(self):
        """
        Tests that the address rewriting is not reversed with an alternative quote if
        the domain does not match.
        """
        result = src.milter.processor.unrewrite_email_address(
            ("Some One", "someone~40example.com@dmarc.example.com"), "example.com", "~"
        )
        assert result == "Some One <someone~40example.com@dmarc.example.com>"

    def test_address_unquoting(self):
        """
        Tests that the address is unquoted correctly.
        """
        result = src.milter.processor.unquote_email_address("someone=40example.com")
        assert result == "someone@example.com"

    def test_address_unquoting_with_alt_quote(self):
        """
        Tests that the address is unquoted correctly with an alternative quote.
        """
        result = src.milter.processor.unquote_email_address(
            "someone~40example.com", "~"
        )
        assert result == "someone@example.com"

    def test_extract_parts(self):
        """
        Test that the mail parts are returned correctly from an email address.
        """
        assert (
            src.milter.processor.extract_parts("someone+foo@example.com")
            == ["someone+foo", "example.com"]
        )

    def test_domain_extraction(self):
        """
        Test that the domain is returned correctly from an email address.
        """
        assert (
            src.milter.processor.extract_domain("someone+foo@example.com")
            == "example.com"
        )

    def test_local_part_extraction(self):
        """
        Test that the local part is returned correctly from an email address.
        """
        assert (
            src.milter.processor.extract_localpart("someone+foo@example.com")
            == "someone+foo"
        )
