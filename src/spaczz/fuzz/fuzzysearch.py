"""Module for FuzzySearch class. A framework for fuzzy matching in spaCy Doc objects."""
from itertools import chain
from typing import Dict, Iterable, List, Optional, Tuple, Union
import warnings

from spacy.tokens import Doc

from .fuzzyconfig import FuzzyConfig
from ..exceptions import FlexWarning, FuzzyPrecheckWarning


class FuzzySearch:
    """Class for fuzzy matching in spacy Docs.

    Fuzzy matching is done on the token level.
    The class provides methods for finding the best fuzzy match
    span in a Doc object, the n best fuzzy matched spans in a Doc,
    and fuzzy matching between any two given strings.

    Attributes:
        _config (FuzzyConfig): The FuzzyConfig object tied to an instance
            of FuzzySearch.
    """

    def __init__(self, config: Union[str, FuzzyConfig] = "default") -> None:
        """Initializes fuzzy search with the given config.

        Args:
            config: Provides predefind fuzzy matching and span trimming functions.
                Uses the default config if "default", an empty config if "empty",
                or a custom config by passing a FuzzyConfig object.
                Default is "default".

        Raises:
            TypeError: If config is not a FuzzyConfig object.
        """
        if config == "default":
            self._config = FuzzyConfig(empty=False)
        elif config == "empty":
            self._config = FuzzyConfig(empty=True)
        else:
            if isinstance(config, FuzzyConfig):
                self._config = config
            else:
                raise TypeError(
                    (
                        "config must be one of the strings 'default' or 'empty',",
                        "or a FuzzyConfig object not,",
                        f"{config} of type: {type(config)}.",
                    )
                )

    def best_match(
        self,
        doc: Doc,
        query: Doc,
        fuzzy_func: str = "simple",
        min_r1: int = 30,
        min_r2: int = 75,
        ignore_case: bool = True,
        flex: Union[str, int] = "default",
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> Union[Tuple[int, int, int], None]:
        """Returns the single best fuzzy match span in a Doc.

        Finds the best fuzzy match span in doc based on the query,
        assuming the minimum match ratios (min_r1 and min_r2) are met,
        If more than one match has the same ratio,
        the earliest match will be returned.

        Args:
            doc: Doc object to search over.
            query: Doc object to fuzzy match against doc.
            fuzzy_func: Key name of fuzzy matching function to use.
                Default is "simple".
            min_r1: Minimum fuzzy match ratio required for
                selection during the intial search over doc.
                This should be lower than min_r2 and "low" in general
                because match span boundaries are not flexed initially.
                0 means all spans of query length in doc will
                have their boundaries flexed and will be recompared
                during match optimization.
                Lower min_r1 will result in more fine-grained matching
                but will run slower. Default is 25.
            min_r2: Minimum fuzzy match ratio required for
                selection during match optimization.
                Should be higher than min_r1 and "high" in general
                to ensure only quality matches are returned.
                Default is 75.
            ignore_case: If strings should be lower-cased before
                fuzzy matching or not. Default is True.
            flex: Number of tokens to move match span boundaries
                left and right during match optimization.
                Default is "default".
            trimmers: Optional iterable of direction agnostic
                span trimmer key names. Default is None.
            start_trimmers: Optional iterable of start index
                span trimmer key names. Default is None.
            end_trimmers: Optional iterable of end index
                span trimmer key names. Default is None.

        Returns:
            A tuple of the match span's start index,
            end index, and fuzzy match ratio or None.

        Raises:
            TypeError: doc must be a Doc object.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp.make_doc("G-rant Anderson lives in TN.")
            >>> query = nlp.make_doc("Grant Andersen")
            >>> fs.best_match(doc, query)
            (0, 4, 90)
        """
        if not isinstance(doc, Doc):
            raise TypeError("doc must be a Doc object.")
        query = self._precheck_query(query, trimmers, start_trimmers, end_trimmers)
        flex = self._calc_flex(query, flex)
        match_values = self._scan_doc(doc, query, fuzzy_func, min_r1, ignore_case)
        pos = self._index_max(match_values)
        if pos is not None:
            match = self._adjust_left_right_positions(
                doc,
                query,
                match_values,
                pos,
                fuzzy_func,
                min_r2,
                ignore_case,
                flex,
                trimmers,
                start_trimmers,
                end_trimmers,
            )
            return match
        else:
            return None

    def match(
        self, str1: str, str2: str, fuzzy_func: str = "simple", ignore_case: bool = True
    ) -> int:
        """Peforms fuzzy matching between two strings.

        Applies the given fuzzy matching algorithm (fuzzy_func)
        to two strings and returns the resulting fuzzy ratio.

        Args:
            str1: First string for comparison.
            str2: Second string for comparison.
            fuzzy_func: Key name of fuzzy matching function to use.
                "simple" by default.
            ignore_case: Whether to lower-case str1 and str2
                before comparison or not. Default is True.

        Returns:
            The fuzzy ratio between a and b.

        Example:
            >>> from spaczz.fuzz import FuzzySearch
            >>> fs = FuzzySearch()
            >>> fs.match("spaczz", "spacy")
            73
        """
        if ignore_case:
            str1 = str1.lower()
            str2 = str2.lower()
        return self._config.get_fuzzy_func(fuzzy_func, ignore_case)(str1, str2)

    def multi_match(
        self,
        doc: Doc,
        query: Doc,
        n: int = 0,
        fuzzy_func: str = "simple",
        min_r1: int = 25,
        min_r2: int = 75,
        ignore_case: bool = True,
        flex: Union[str, int] = "default",
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> List[Optional[Tuple[int, int, int]]]:
        """Returns the n best fuzzy matches in a Doc.

        Finds the n best fuzzy matches in doc based on the query,
        assuming the minimum match ratios (r1 and r2) are met.
        Matches will be sorted by matching score, then start index.

        Args:
            doc: Doc object to search over.
            query: Doc object to fuzzy match against doc.
            n: Max number of matches to return.
                If n is 0 all matches will be returned.
                Defualt is 0.
            fuzzy_func: Key name of fuzzy matching function to use.
                Default is "simple".
            min_r1: Minimum fuzzy match ratio required for
                selection during the intial search over doc.
                This should be lower than min_r2 and "low" in general
                because match span boundaries are not flexed initially.
                0 means all spans of query length in doc will
                have their boundaries flexed and will be recompared
                during match optimization.
                Lower min_r1 will result in more fine-grained matching
                but will run slower. Default is 25.
            min_r2: Minimum fuzzy match ratio required for
                selection during match optimization.
                Should be higher than min_r1 and "high" in general
                to ensure only quality matches are returned.
                Default is 75.
            ignore_case: If strings should be lower-cased before
                fuzzy matching or not. Default is True.
            flex: Number of tokens to move match span boundaries
                left and right during match optimization.
                Default is "default".
            trimmers: Optional iterable of direction agnostic
                span trimmer key names. Default is None.
            start_trimmers: Optional iterable of start index
                span trimmer key names. Default is None.
            end_trimmers: Optional iterable of end index
                span trimmer key names. Default is None.

        Returns:
            A list of tuples of match span start indices,
            end indices, and fuzzy match ratios.

        Raises:
            TypeError: doc must be a Doc object.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp.make_doc(
                "chiken from Popeyes is better than chken from Chick-fil-A"
                )
            >>> query = nlp.make_doc("chicken")
            >>> fs.multi_match(doc, query, ignore_case=False)
            [(0, 1, 92), (6, 7, 83)]
        """
        if not isinstance(doc, Doc):
            raise TypeError("doc must be a Doc object.")
        if n == 0:
            n = int(len(doc) / len(query) + 2)
        query = self._precheck_query(query, trimmers, start_trimmers, end_trimmers)
        flex = self._calc_flex(query, flex)
        match_values = self._scan_doc(doc, query, fuzzy_func, min_r1, ignore_case)
        positions = self._indice_maxes(match_values, n)
        matches = [
            self._adjust_left_right_positions(
                doc,
                query,
                match_values,
                pos,
                fuzzy_func,
                min_r2,
                ignore_case,
                flex,
                trimmers,
                start_trimmers,
                end_trimmers,
            )
            for pos in positions
        ]
        matches = [match for match in matches if match]
        matches = sorted(matches, key=lambda x: (-x[2], x[0]))
        matches = self._filter_overlapping_matches(matches)
        return matches

    def _adjust_left_right_positions(
        self,
        doc: Doc,
        query: Doc,
        match_values: Dict[int, int],
        pos: int,
        fuzzy_func: str,
        min_r2: int,
        ignore_case: bool,
        flex: int,
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> Union[Tuple[int, int, int], None]:
        """Optimizes a fuzzy match by flexing match span boundaries.

        For a span match from _scan_doc that has fuzzy ratio
        greater than or equal to min_r1 the span boundaries
        will be extended both left and right by flex number
        of tokens and fuzzy matched to the original query.
        The optimal start and end index for the span
        are then run through optional trimming rules enforcement
        before being returned along with the span's fuzzy ratio.

        Args:
            doc: Doc object being searched over.
            query: Doc object to fuzzy match against doc.
            match_values: Dict of initial match spans
                start indices and fuzzy ratios.
            pos: Start index of span being optimized.
            fuzzy_func: Key name of fuzzy matching function to use.
            min_r2: Minimum fuzzy match ratio required
                to pass optimization. This should be high enough
                to only return quality matches.
            ignore_case: If strings should be lower-cased before
                fuzzy matching or not.
            flex: Number of tokens to move match span boundaries
                left and right during match optimization.
            trimmers: Optional iterable of direction agnostic
                span trimmer key names. Default is None.
            start_trimmers: Optional iterable of start index
                span trimmer key names. Default is None.
            end_trimmers: Optional iterable of end index
                span trimmer key names. Default is None.

        Returns:
            A tuple of left boundary index,
            right boudary index, and fuzzy match ratio
            or None.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp.make_doc("Patient was prescribed Zithromax tablets.")
            >>> query = nlp.make_doc("zithromax tablet")
            >>> match_values = {3: 100}
            >>> fs._adjust_left_right_positions(doc, query, match_values,
                pos=3, fuzzy_func="simple", min_r2=70, ignore_case=True,
                flex=2)
            (3, 5, 97)
        """
        p_l, bp_l = [pos] * 2
        p_r, bp_r = [pos + len(query)] * 2
        bmv_l = match_values[p_l]
        bmv_r = match_values[p_l]
        if flex:
            for f in range(1, flex + 1):
                ll = self.match(
                    query.text, doc[p_l - f : p_r].text, fuzzy_func, ignore_case
                )
                if (ll > bmv_l) and (p_l - f >= 0):
                    bmv_l = ll
                    bp_l = p_l - f
                lr = self.match(
                    query.text, doc[p_l + f : p_r].text, fuzzy_func, ignore_case
                )
                if (lr > bmv_l) and (p_l + f < p_r):
                    bmv_l = lr
                    bp_l = p_l + f
                rl = self.match(
                    query.text, doc[p_l : p_r - f].text, fuzzy_func, ignore_case
                )
                if (rl > bmv_r) and (p_r - f > p_l):
                    bmv_r = rl
                    bp_r = p_r - f
                rr = self.match(
                    query.text, doc[p_l : p_r + f].text, fuzzy_func, ignore_case
                )
                if rr > bmv_r and (p_r + f <= len(doc)):
                    bmv_r = rr
                    bp_r = p_r + f
        bp_l, bp_r = self._enforce_trimming_rules(
            doc, bp_l, bp_r, trimmers, start_trimmers, end_trimmers
        )
        if None not in (bp_l, bp_r):
            r = self.match(query.text, doc[bp_l:bp_r].text, fuzzy_func, ignore_case)
            if r >= min_r2:
                return (bp_l, bp_r, r)
        return None

    def _enforce_end_trimmers(
        self,
        doc: Doc,
        bp_l: int,
        bp_r: int,
        trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> Union[int, None]:
        """Enforces trimming rules to the end index of the match span.

        Will move the span end index backwards until the
        trimming functions return False -
        returning a new end index,
        or until the start index equals the end index -
        returning None.

        Args:
            doc: The Doc object being searched over.
            bp_l: Span start index.
            bp_r: Span end index.
            trimmers: Optional iterable of direction agnostic
                span trimmer key names.
            end_trimmers: Optional iterable of end index
                span trimmer key names.

        Returns:
            Integer of new end index or None.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp("we don't want no punctuation.")
            >>> fs._enforce_end_trimmers(doc, 5, 7, end_trimmers=["punct"])
            6
        """
        trimmer_funcs, trimmer_keys = self._config.get_trimmers(
            "end", trimmers, end_trimmers=end_trimmers
        )
        if trimmer_funcs:
            while any([func(doc[bp_r - 1]) for func in trimmer_funcs]):
                if bp_r - 1 <= bp_l:
                    return None
                bp_r -= 1
        return bp_r

    def _enforce_start_trimmers(
        self,
        doc: Doc,
        bp_l: int,
        bp_r: int,
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
    ) -> Union[int, None]:
        """Enforces trimming rules to the start index of the match span.

        Will move the span start index forward until the
        trimming functions return False -
        returning a new start index,
        or until the start index equals the end index -
        returning None.

        Args:
            doc: The Doc object being searched over.
            bp_l: Span start index.
            bp_r: Span end index.
            trimmers: Optional iterable of direction agnostic
                span trimmer key names.
            start_trimmers: Optional iterable of start index
                span trimmer key names.

        Returns:
            Integer of new start index or None.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp("this starts with a stop word")
            >>> fs._enforce_start_trimmers(doc, 0, 2, start_trimmers=["stop"])
            1
        """
        trimmer_funcs, trimmer_keys = self._config.get_trimmers(
            "start", trimmers, start_trimmers
        )
        if trimmer_funcs:
            while any([func(doc[bp_l]) for func in trimmer_funcs]):
                if bp_l >= bp_r:
                    return None
                bp_l += 1
                if bp_l == len(doc):
                    return None
        if bp_l >= bp_r:
            return None
        else:
            return bp_l

    def _enforce_trimming_rules(
        self,
        doc: Doc,
        bp_l: int,
        bp_r: int,
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> Tuple[Union[int, None], Union[int, None]]:
        """Span boundary rules are enforced on optimized fuzzy match.

        After fuzzy match optimization, any start-only, end-only,
        or direction agnostic trimming rules are applied to the
        start and end indices of the match span to prevent
        unwanted tokens from populating the span.

        Args:
            doc: Doc object being searched over.
            bp_l: Span start index.
            bp_r: Span end index.
            trimmers: Optional iterable of direction agnostic
                span trimmer key names.
            start_trimmers: Optional iterable of start index
                span trimmer key names.
            end_trimmers: Optional iterable of end index
                span trimmer key names.

        Returns:
            The new span start index or None
            and the new span end index or None
            as a tuple. Only one of the two values
            will be None.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> doc = nlp("The token we are looking for is: xenomorph.")
            >>> fs._enforce_trimming_rules(doc, 7, 10, trimmers=["punct"])
            (8, 9)
        """
        bp_l = self._enforce_start_trimmers(doc, bp_l, bp_r, trimmers, start_trimmers)
        if bp_l:
            bp_r = self._enforce_end_trimmers(doc, bp_l, bp_r, trimmers, end_trimmers)
        return bp_l, bp_r

    def _precheck_query(
        self,
        query: Doc,
        trimmers: Optional[Iterable[str]] = None,
        start_trimmers: Optional[Iterable[str]] = None,
        end_trimmers: Optional[Iterable[str]] = None,
    ) -> Doc:
        """Validates the query Doc before fuzzy matching.

        Ensures the query is a Doc object and
        checks if any of the trimmer functions affect the query.

        Args:
            query: Doc to fuzzy match against another Doc object.
            trimmers: Optional iterable of direction agnostic
                span trimmer key names.
            start_trimmers: Optional iterable of start index
                span trimmer key names.
            end_trimmers: Optional iterable of end index
                span trimmer key names.

        Returns:
            A Doc object.

        Raises:
            TypeError: The query is not a Doc object.

        Warnings:
            UserWarning:
                If trimmer rules will affect the query.

        Example:
            >>> import spacy
            >>> from spacy.tokens import Doc
            >>> from spaczz.fuzz import FuzzySearch
            >>> nlp = spacy.blank("en")
            >>> fs = FuzzySearch()
            >>> query = nlp("This is a query.")
            >>> precheck_query = fs._precheck_query(query)
            >>> isinstance(precheck_query, Doc)
            True
        """
        if not isinstance(query, Doc):
            raise TypeError("The query must be a Doc object.")
        start_trimmer_funcs, _ = self._config.get_trimmers(
            "start", trimmers, start_trimmers
        )
        end_trimmer_funcs, _ = self._config.get_trimmers(
            "end", trimmers, end_trimmers=end_trimmers
        )
        if any([func(query[0]) for func in start_trimmer_funcs]) or any(
            [func(query[-1]) for func in end_trimmer_funcs]
        ):
            warnings.warn(
                """One or more trimmer rules will affect the query,\n
                    which will likely lead to unexpected fuzzy matching behavior.\n
                    Either change the query or trimmer rules to remedy this.""",
                FuzzyPrecheckWarning,
            )
        return query

    def _scan_doc(
        self, doc: Doc, query: Doc, fuzzy_func: str, min_r1: int, ignore_case: bool
    ) -> Dict[int, int]:
        """Returns a Dict of potential match start indices and fuzzy ratios.

        Iterates through the doc by spans of query length,
        and fuzzy matches each span gainst query.

        If a match span's fuzzy ratio is greater than or equal to the
        min_r1 it is added to a dict with it's start index
        as the key and it's ratio as the value.

        Args:
            doc: Doc object to search over.
            query: Doc object to fuzzy match against doc.
            fuzzy_func: Key name of fuzzy matching function to use.
            min_r1: Minimum fuzzy match ratio required for
                selection during the intial search over doc.
                This should be lower than min_r2 and "low" in general
                because match span boundaries are not flexed here.
                0 means all spans of query length in doc will
                have their boundaries flexed and will be recompared
                during match optimization.
                Lower min_r1 will result in more fine-grained matching
                but will run slower.
            ignore_case: If strings should be lower-cased before
                fuzzy matching or not.

        Returns:
            A Dict of start index, fuzzy match ratio pairs.

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import FuzzySearch
            >>> fs = FuzzySearch()
            >>> nlp = spacy.blank("en")
            >>> doc = nlp.make_doc("Don't call me Sh1rley.")
            >>> query = nlp.make_doc("Shirley")
            >>> fs._scan_doc(doc, query,
                fuzzy_func="simple", min_r1=50,
                ignore_case=True)
            {4: 86}
        """
        match_values = dict()
        i = 0
        while i + len(query) <= len(doc):
            match = self.match(
                query.text, doc[i : i + len(query)].text, fuzzy_func, ignore_case
            )
            if match >= min_r1:
                match_values[i] = match
            i += 1
        return match_values

    @staticmethod
    def _calc_flex(query: Doc, flex: Union[str, int]) -> int:
        """Returns flex value based on initial value and query.

        By default flex is set to the legth of query.
        If flex is a value greater than query,
        flex will be set to 1 instead.

        Args:
            query: The Doc object to fuzzy match with.
            flex: Either "default" or an integer value.

        Returns:
            The new flex value.

        Raises:
            TypeError: If flex is not "default" or an int.

        Warnings:
            UserWarning:
                If flex is > len(query).

        Example:
            >>> import spacy
            >>> from spaczz.fuzz import fuzzysearch
            >>> fs = fuzzysearch.FuzzySearch()
            >>> query = spacy.blank("en")("Test query.")
            >>> fs._calc_flex(query, "default")
            3
        """
        if flex == "default":
            flex = len(query)
        elif isinstance(flex, int):
            if flex > len(query):
                warnings.warn(
                    f"""Flex of size {flex} is greater than len(query).\n
                        Setting flex to the default flex = len(query)""",
                    FlexWarning,
                )
                flex = len(query)
        else:
            raise TypeError("Flex must be either the string 'default' or an integer.")
        return flex

    @staticmethod
    def _filter_overlapping_matches(
        matches: List[Optional[Tuple[int, int, int]]]
    ) -> List[Optional[Tuple[int, int, int]]]:
        """Prevents multiple fuzzy match spans from overlapping.

        Expects matches to be pre-sorted by descending ratio
        then ascending start index.
        If more than one match span includes the same tokens
        the first of these match spans in matches is kept.

        Args:
            matches: List of match span tuples
                (start_index, end_index, fuzzy ratio).

        Returns:
            The filtered list of match span tuples.

        Example:
            >>> from spaczz.fuzz import FuzzySearch
            >>> fs = FuzzySearch()
            >>> matches = [(1, 3, 80), (1, 2, 70)]
            >>> fs._filter_overlapping_matches(matches)
            [(1, 3, 80)]
        """
        filtered_matches: List[Optional[Tuple[int, int, int]]] = []
        for match in matches:
            if not set(range(match[0], match[1])).intersection(
                chain(*[set(range(n[0], n[1])) for n in filtered_matches])
            ):
                filtered_matches.append(match)
        return filtered_matches

    @staticmethod
    def _indice_maxes(
        match_values: Dict[int, int], n: int
    ) -> Union[List[int], Dict[int, int]]:
        """Returns the start indices of the n highest ratio fuzzy matches.

        If more than n matches are found the matches will be sorted by
        decreasing ratio value, then increasing start index,
        then the first n will be returned.
        If n is 0, all matches are returned, unordered.

        Args:
            match_values: Dict of unoptimized fuzzy matches in
                start index, fuzzy ratio pairs, or an empty dict.
            n: The maximum number of values to return.
                If 0 all matches are returned unordered.

        Returns:
            List of integer values of the best matches start indices.

        Example:
            >>> from spaczz.fuzz import FuzzySearch
            >>> fs = FuzzySearch()
            >>> fs._indice_maxes({1: 30, 4: 50, 5: 50, 9: 100}, 3)
            [9, 4, 5]
        """
        if n:
            return sorted(match_values, key=lambda x: (-match_values[x], x))[:n]
        else:
            return match_values

    @staticmethod
    def _index_max(match_values: Union[Dict[int, int], Dict]) -> Union[int, None]:
        """Returns the start index of the highest ratio fuzzy match or None.

        If the max ratio applies to multiple indices
        the lowest index will be returned.
        If an empty dictionary is passed, None is returned.

        Args:
            match_values: Dict of potential fuzzy matches
                in start index, fuzzy ratio pairs, or an empty dict.

        Returns:
            Integer value of the best matches' start index or None.

        Example:
            >>> from spaczz.fuzz import FuzzySearch
            >>> fs = FuzzySearch()
            >>> fs._index_max({1:30, 9:100})
            9
        """
        try:
            return sorted(match_values, key=lambda x: (-match_values[x], x))[0]
        except IndexError:
            return None