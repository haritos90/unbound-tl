from gen3tl.catalog.po import KEY_ONLY, SOURCE_FIELD

import submission_support

class KeyOnlySubmissionTest(submission_support.SubmissionTest):
    """The same submissions on key-only catalogs without English."""
    HEADER = {SOURCE_FIELD: KEY_ONLY}
    IMPORT_REFUSAL = "a key-only catalog without its English source catalog"   # web import reads the English
