"""Module for the RegexSearcher class. Does multi-token regex matching in spaCy Docs."""
from typing import List, Tuple, Union

from spacy.tokens import Doc, Span

from .regexconfig import RegexConfig
from ..process import map_chars_to_tokens


class RegexSearcher:
    """Class for multi-token regex matching in spacy Docs.

    Regex matching is done on the character level and then
    mapped back to tokens.

    Attributes:
        _config (RegexConfig): The regex config used with the
            regex searcher.
    """

    def __init__(self, config: Union[str, RegexConfig] = "default") -> None:
        """Initializes the regex searcher with the given config.

        Args:
            config: Provides the class with predefind regex patterns.
                Uses the default config if "default", an empty config if "empty",
                or a custom config by passing a RegexConfig object.
                Default is "default".

        Raises:
            TypeError: If config is not a RegexConfig object.
        """
        if config == "default":
            self._config = RegexConfig(empty=False)
        elif config == "empty":
            self._config = RegexConfig(empty=True)
        else:
            if isinstance(config, RegexConfig):
                self._config = config
            else:
                raise TypeError(
                    (
                        "config must be one of the strings 'default' or 'empty',",
                        "or a RegexConfig object not,",
                        f"{config} of type: {type(config)}.",
                    )
                )

    def match(
        self, doc: Doc, regex_str: str, partial: bool = True, predef: bool = False,
    ) -> List[Tuple[int, int, Tuple[int, int, int]]]:
        """Returns all the regex matches within doc.

        Matches on the character level and then maps matches back
        to tokens. If a character cannot be mapped back to a token it means
        it is a space tokens are split on, which happens when regex matches
        produce leading or trailing whitespace. Confirm your regex pattern
        will not do this to avoid this issue.

        To utilize regex flags, use inline flags.

        Args:
            doc: Doc object to search over.
            regex_str: A string to be compiled to regex,
                or the key name of a predefined regex pattern.
            partial: Whether partial matches should be extended
                to existing span boundaries in doc or not, i.e.
                the regex only matches part of a token or span.
                Default is True.
            predef: Whether regex should be interpreted as a key to
                a predefined regex pattern or not. Default is False.
                The included regexes are:
                "dates"
                "times"
                "phones"
                "phones_with_exts"
                "links"
                "emails"
                "ips"
                "ipv6s"
                "prices"
                "hex_colors"
                "credit_cards"
                "btc_addresses"
                "street_addresses"
                "zip_codes"
                "po_boxes"
                "ssn_number".

        Returns:
            A list of span start index, end index, fuzzy change count tuples.

        Raises:
            TypeError: If regex_str is not a string.

        Example:
            >>> import spacy
            >>> from spaczz.regex import RegexSearcher
            >>> nlp = spacy.blank("en")
            >>> searcher = RegexSearcher()
            >>> doc = nlp.make_doc("My phone number is (555) 555-5555.")
            >>> searcher.match(doc, "phones", predef=True)
            [(4, 10, (0, 0, 0))]
        """
        if isinstance(regex_str, str):
            compiled_regex = self._config.parse_regex(regex_str, predef)
        else:
            raise TypeError(f"regex_str must be a str, not {type(regex_str)}.")
        matches = []
        chars_to_tokens = map_chars_to_tokens(doc)
        for match in compiled_regex.finditer(doc.text):
            start, end = match.span()
            counts = match.fuzzy_counts
            span = doc.char_span(start, end)
            if span:
                matches.append((span, counts))
            else:
                if partial:
                    start_token = chars_to_tokens.get(start)
                    end_token = chars_to_tokens.get(end)
                    if start_token and end_token:
                        span = Span(doc, start_token, end_token + 1)
                        matches.append((span, counts))
        if matches:
            return [(match[0].start, match[0].end, match[1]) for match in matches]
        else:
            return []
