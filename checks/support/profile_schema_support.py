from pathlib import Path
import shutil
import tempfile
from copy import deepcopy

from gen3tl.core import notes
from gen3tl.profile import schema

from project_fixture import literal

HEADER = '[discovery]\nschema = 1\n'

GENERATED = HEADER + '''
[rom]
sha1 = "00112233445566778899aabbccddeeff00112233"
size = 0x1000

[[font]]
name = "main"
glyphs = 0x100
widths = 0x200
count = 8

[keyboard]
base = 0x400
pages = 2

[strings]
include = [0x10, 0x20]

[[fact]]
id = "rom.sha1"
tier = "shape"
source = "identity 1"
evidence = {method = "header", sentence = "SHA-1 of the whole image."}

[[fact]]
id = "rom.size"
tier = "shape"
source = "identity 1"
evidence = {method = "header", sentence = "File size."}

[[fact]]
id = "font[name=main]"
tier = "crossref"
source = "fonts 1"
evidence = {method = "literal-pool", anchors = [0x100, 0x200], code_sites = [0x6594], counts = {pairs = 1}, sentence = "Pool at 0x6594 pairs the glyphs with the widths."}

[[fact]]
id = "keyboard"
tier = "crossref"
source = "keyboard 1"
evidence = {method = "accessor", sentence = "The page reader indexes 0x400."}

[[fact]]
id = "strings.include[0x10]"
tier = "crossref"
source = "strings 1"
evidence = {sentence = "Referenced by a literal pool."}

[[fact]]
id = "strings.include[0x20]"
tier = "crossref"
source = "strings 1"
evidence = {sentence = "Referenced by a script."}
'''

OVERLAY = '''# hand-proven
[rom]
name = "Example"
size = 0x1000

[[font]]
name = "main"
count = 9
evidence = "the renderer reads nine glyphs"

[[font]]
name = "small"
glyphs = 0x300
evidence = "pool at 0x64C4"

[keyboard]
base = 0x400
pages = 2
rows = 4
evidence = "page reader at 0x8000"

[strings]
include = [0x20, 0x30]

[[fact]]
id = "font[name=small]"
tier = "ingame"
'''

def write_dir(root: Path, name: str = "game-1.2.3", generated: str = GENERATED, overlay: str | None = OVERLAY) -> Path:
    path = root / name
    path.mkdir()
    (path / "profile.toml").write_text(generated, encoding="utf-8")
    if overlay is not None:
        (path / "overlay.toml").write_text(overlay, encoding="utf-8")
    return path

class ProfileNotesTest:
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = write_dir(self.tmp, generated=HEADER, overlay="")

    def note(self, fact_id, value, field="evidence", **fields):
        return {"id": "proof", "subject": {"kind": "profile_fact", "id": fact_id},
                "scope": {"kind": "shared"}, "status": "unreviewed", "facts": ["Measured reader."],
                "binding": {"kind": "profile_fact", "id": fact_id,
                            "value_sha256": schema.value_digest(value), "field": field}, **fields}

    def write(self, data, records):
        lines = [f"{key} = {literal(value)}" for key, value in data.items()]
        for record in records:
            lines.append("[[fact]]")
            lines.extend(f"{key} = {literal(value)}" for key, value in record.items() if key != "notes")
            for note in record.get("notes", []):
                lines.append("[[fact.notes]]")
                lines.extend(f"{key} = {literal(value)}" for key, value in note.items())
            if record.get("notes") == []:
                lines.append("notes = []")
        (self.path / schema.OVERLAY).write_text("\n".join(lines), encoding="utf-8")

    def record(self, fact_id, value, field="evidence", **fields):
        return {"id": fact_id, "notes_schema": notes.SCHEMA,
                "notes": [self.note(fact_id, value, field)], **fields}

    def migrated(self, value, status):
        value = deepcopy(value)
        fields = []

        def clear(item, path=""):
            if isinstance(item, dict):
                for key, child in item.items():
                    pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
                    if schema.is_prose(key) and isinstance(child, str):
                        fields.append(pointer)
                        item[key] = ""
                    else:
                        clear(child, pointer)
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    clear(child, f"{path}/{index}")

        clear(value)
        data = {"table": [value]}
        fact = schema.facts(data)[0]
        template = self.note(fact.id, value, status=status, facts=["Measured reader.", "Verified boundary."])
        records = [dict(template, id=f"proof-{index}", binding=dict(template["binding"], field=field))
                   for index, field in enumerate(fields)]
        self.write(data, [{"id": fact.id, "notes_schema": notes.SCHEMA, "notes": records}])
        return schema.load(self.path)["table"][0]
