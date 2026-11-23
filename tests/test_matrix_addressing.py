import pytest
from matrix import addressed_names

ALIVE = ["Pale Rest", "Dark Hinge", "Warm Trace"]


@pytest.mark.parametrize("body,expected", [
    ("A question for Pale Rest: how are you?", ["Pale Rest"]),
    ("for pale rest, please answer", ["Pale Rest"]),
    ("FOR   DARK    HINGE: hello", ["Dark Hinge"]),
    ("for Dark Hinge and also for Pale Rest", ["Dark Hinge", "Pale Rest"]),
    ("for Pale Rest, for Pale Rest", ["Pale Rest"]),
    ("Pale Rest, what do you think?", []),            # a name without "for" is not an address
    ("I did this before Pale Rest arrived", []),      # "for" inside another word
    ("for Pale Restless things", []),                 # the name must be whole
    ("for Somebody Else", []),                        # not alive: nobody is addressed
    ("Hello everyone", []),
])
def test_addressed_names_finds_for_name_case_insensitively(body, expected):
    assert addressed_names(body, ALIVE) == expected
