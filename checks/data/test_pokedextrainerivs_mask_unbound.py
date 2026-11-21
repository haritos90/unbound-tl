import unittest

from gen3tl.core.thumb import decode
from gen3tl.data import pokedextrainerivs as iv
from gen3tl.profile.profile import Profile

from rom_support import needs_rom, rom_path
from pokedextrainerivs_support import trainer

MASK32 = 0xFFFFFFFF


UNKNOWN = ("u",)


def constant(value):
    return ("c", value & MASK32)


class Domain:
    """Allowed values of one symbol as disjoint closed intervals."""

    def __init__(self, lo=0, hi=0xFFFF, parts=None):
        self.parts = parts if parts is not None else ([(lo, hi)] if lo <= hi else [])

    @staticmethod
    def cut(parts, first, last):
        result = []
        for lo, hi in parts:
            if hi < first or lo > last:
                result.append((lo, hi))
                continue
            if lo < first:
                result.append((lo, first - 1))
            if hi > last:
                result.append((last + 1, hi))
        return result

    def empty(self):
        return not self.parts

    def size(self):
        return sum(hi - lo + 1 for lo, hi in self.parts)

    def single(self):
        if len(self.parts) == 1 and self.parts[0][0] == self.parts[0][1]:
            return self.parts[0][0]
        return None

    def values(self):
        for lo, hi in self.parts:
            yield from range(lo, hi + 1)

    def keep(self, first, last):
        return Domain(parts=[(max(lo, first), min(hi, last))
                             for lo, hi in self.parts if not (hi < first or lo > last)])

    def drop(self, first, last):
        return Domain(parts=self.cut(self.parts, first, last))


class MaskState:
    def __init__(self):
        self.r = [UNKNOWN] * 16
        self.stack = {}
        self.cmp = None
        self.dom = {}
        self.events = []
        self.sp = 0
        self.steps = 0
        self.carry = None

    def copy(self):
        state = MaskState()
        state.r = list(self.r)
        state.stack = dict(self.stack)
        state.cmp = self.cmp
        state.dom = dict(self.dom)
        state.events = list(self.events)
        state.sp = self.sp
        state.steps = self.steps
        state.carry = self.carry
        return state


def symbolic_add(left, right):
    if left[0] == right[0] == "c":
        return constant(left[1] + right[1])
    if left[0] == "c":
        left, right = right, left
    if right[0] == "c":
        offset = right[1] if right[1] < 0x80000000 else right[1] - (1 << 32)
        if left[0] in ("s", "p"):
            return (left[0], left[1], left[2] + offset)
    return UNKNOWN


class MaskWalk:
    """Bounded path-sensitive execution of the declared adjustment span."""

    BAD_EVENTS = {"branch_unknown", "case_unknown", "case_unbounded", "indirect_unknown", "left_span",
                  "loop_unresolved", "mask_nonconstant", "setmon_unknown_field", "step_limit", "unhandled"}

    def __init__(self, block, data):
        self.data = data
        stage = next(stage for stage in block["stages"] if stage["operation"] == "packed_masks")
        addresses = [offset - iv.ROM_BASE for offset in stage["operation_offsets"]]
        self.span = next(span for span in block["spans"] if any(
            span["offset"] <= address < span["offset"] + span["size"] for address in addresses))
        self.start = self.span["offset"]
        self.end = self.start + self.span["size"]
        writes = self.span.get("iv_writes", [])
        if len(writes) != 1:
            raise ValueError("packed mask routine must declare one IV field")
        self.field = writes[0]["field"]
        self.write_calls = {address for address in addresses if decode(data, address).mnemonic == "bl"}
        if not self.write_calls:
            raise ValueError("packed mask stage declares no setter call")
        self.difficulties = len(block["difficulties"])
        self.trainer_count = next(table["count"] for table in block["tables"] if table["name"] == "trainer_records")
        self.paths = []
        self.loop_exits = self.find_loop_exits()
        self.getter_target = None
        self.difficulty_target = None

    def in_span(self, address):
        return self.start <= address < self.end

    def literal(self, address):
        return int.from_bytes(self.data[address:address + 4], "little")

    def find_loop_exits(self):
        instructions = []
        address = self.start
        while address < self.end:
            instruction = decode(self.data, address)
            instructions.append(instruction)
            address += instruction.size
        exits = {}
        for branch in instructions:
            if branch.mnemonic != "b" or branch.condition is not None or not self.in_span(branch.target) \
                    or branch.target >= branch.address or branch.address - branch.target > 64:
                continue
            body = [instruction for instruction in instructions
                    if branch.target <= instruction.address < branch.address]
            targets = [instruction.target for instruction in body if instruction.mnemonic == "bl"
                       and self.in_span(instruction.target)
                       and not branch.target <= instruction.target < branch.address]
            external = any(instruction.mnemonic == "bl" and not self.in_span(instruction.target)
                           for instruction in body)
            tested = any(instruction.mnemonic == "tst" for instruction in body)
            stack_write = any(instruction.mnemonic in ("str", "strh", "strb") and instruction.rn == 13
                              for instruction in body)
            if targets and external and tested and not stack_write:
                exits[branch.target] = targets[0]
        return exits

    def run(self, max_steps=40000, max_paths=2048):
        state = MaskState()
        state.r[0] = ("s", "trainer", 0)
        state.r[1] = ("p", "mon", 0)
        state.r[13] = ("p", "sp", 0)
        state.r[14] = constant(0xDEAD)
        state.dom["trainer"] = Domain(0, self.trainer_count - 1)
        work = [(self.start, state)]
        while work:
            if len(self.paths) >= max_paths:
                raise ValueError("packed mask symbolic path limit")
            pc, state = work.pop()
            work.extend(self.step_until_fork(pc, state, max_steps))
        return self.paths

    def resolve(self, state, value):
        if value[0] == "s" and value[1] in state.dom:
            selected = state.dom[value[1]].single()
            if selected is not None:
                return constant(selected + value[2])
        return value

    @staticmethod
    def eval_const(left, right, condition):
        signed_left = left - (1 << 32) if left & 0x80000000 else left
        signed_right = right - (1 << 32) if right & 0x80000000 else right
        result = (left - right) & MASK32
        return {"eq": left == right, "ne": left != right, "cs": left >= right, "cc": left < right,
                "hi": left > right, "ls": left <= right, "ge": signed_left >= signed_right,
                "lt": signed_left < signed_right, "gt": signed_left > signed_right,
                "le": signed_left <= signed_right, "mi": bool(result & 0x80000000),
                "pl": not (result & 0x80000000)}[condition]

    def constrain_cmp(self, state, name, offset, value, condition, taken):
        if not taken:
            condition = {"eq": "ne", "ne": "eq", "cs": "cc", "cc": "cs", "hi": "ls", "ls": "hi",
                         "ge": "lt", "lt": "ge", "gt": "le", "le": "gt", "mi": "pl", "pl": "mi"}[condition]
        if condition in ("mi", "pl"):
            condition = "lt" if condition == "mi" else "ge"
        domain = state.dom.get(name, Domain())
        target = value - offset
        big = 10**9
        if condition == "eq":
            selected = domain.keep(target, target)
        elif condition == "ne":
            selected = domain.drop(target, target)
        elif condition in ("gt", "ge", "lt", "le"):
            selected = {"gt": domain.keep(target + 1, big), "ge": domain.keep(target, big),
                        "lt": domain.keep(-big, target - 1), "le": domain.keep(-big, target)}[condition]
        else:
            unsigned = value & MASK32
            wrapped = domain.keep(-big, -offset - 1)
            normal = domain.keep(-offset, big)
            if condition == "hi":
                selected = Domain(parts=wrapped.parts + normal.keep(unsigned - offset + 1, big).parts)
            elif condition == "cs":
                selected = Domain(parts=wrapped.parts + normal.keep(unsigned - offset, big).parts)
            elif condition == "cc":
                selected = normal.keep(-big, unsigned - offset - 1)
            elif condition == "ls":
                selected = normal.keep(-big, unsigned - offset)
            else:
                raise ValueError(condition)
            selected = Domain(parts=sorted(selected.parts))
        if selected.empty():
            return False
        state.dom[name] = selected
        return True

    def apply(self, state, kind, left, right, condition, taken):
        if kind == "tst":
            value = left
            if value[0] == "c" and condition in ("eq", "ne"):
                zero = value[1] == 0
                return {"eq": zero, "ne": not zero}[condition] == taken
            if condition in ("eq", "ne") and value[0] == "s" and value[2] == 0:
                return self.constrain_cmp(state, value[1], 0, 0, "eq" if (condition == "eq") == taken else "ne", True)
            if condition in ("mi", "pl") and value[0] == "c":
                negative = bool(value[1] & 0x80000000)
                return (negative if condition == "mi" else not negative) == taken
            if value[0] == "s" and value[1].startswith("bit:"):
                return True
            state.events.append(("branch_unknown", condition, repr(value)))
            return True
        if left[0] == right[0] == "c":
            return self.eval_const(left[1], right[1], condition) == taken
        if left[0] == "s" and right[0] == "c":
            value = right[1] - (1 << 32) if right[1] >= 0x80000000 else right[1]
            return self.constrain_cmp(state, left[1], left[2], value, condition, taken)
        if left[0] == "c" and right[0] == "s":
            reversed_condition = {"eq": "eq", "ne": "ne", "hi": "cc", "ls": "cs", "cs": "ls", "cc": "hi",
                                  "gt": "lt", "le": "ge", "ge": "le", "lt": "gt"}[condition]
            return self.constrain_cmp(state, right[1], right[2], left[1], reversed_condition, taken)
        state.events.append(("branch_unknown", condition, repr(left), repr(right)))
        return True

    def cond_fork(self, state, condition, target, following):
        comparison = state.cmp
        if comparison is None:
            state.events.append(("branch_unknown", condition))
            return [(target, state.copy()), (following, state.copy())]
        kind, left, right = comparison
        result = []
        for taken in (True, False):
            selected = state.copy()
            if self.apply(selected, kind, left, right, condition, taken):
                result.append((target if taken else following, selected))
        return result

    def case_entry(self, helper):
        signature = self.data[helper:helper + 20].hex()
        if "5c09" in signature or "095c" in signature:
            return lambda table, value: 2 * self.data[table + value]
        if "5609" in signature:
            return lambda table, value: 2 * (self.data[table + value] - 256 if self.data[table + value] > 127
                                            else self.data[table + value])
        if "5a09" in signature or "095a" in signature or "5a40" in signature:
            return lambda table, value: 2 * int.from_bytes(
                self.data[table + 2 * value:table + 2 * value + 2], "little")
        return None

    def case(self, state, pc, entry):
        index = self.resolve(state, state.r[0])
        table = pc + 4
        if index[0] == "c":
            values = [index[1]]
        elif index[0] == "s":
            domain = state.dom.get(index[1], Domain())
            if domain.size() > 1024:
                state.events.append(("case_unbounded", pc + iv.ROM_BASE))
                self.paths.append(state)
                return []
            values = [value + index[2] for value in domain.values()]
        else:
            state.events.append(("case_unknown", pc + iv.ROM_BASE))
            self.paths.append(state)
            return []
        result = []
        for value in values:
            selected = state.copy()
            if index[0] == "s" and not self.constrain_cmp(selected, index[1], 0, value - index[2], "eq", True):
                continue
            result.append((table + entry(table, value), selected))
        return result

    def call(self, state, at, target):
        args = [self.resolve(state, state.r[index]) for index in range(4)]
        result = ("s", f"ret:{target:07X}@{at + iv.ROM_BASE:08X}", 0)
        if at in self.write_calls:
            field = args[1]
            value = state.stack.get(args[2][2]) if args[2][0] == "p" and args[2][1] == "sp" else None
            if field[0] != "c":
                state.events.append(("setmon_unknown_field", repr(field), at + iv.ROM_BASE))
            elif field[1] == self.field:
                state.events.append(("mask", field[1], value, at + iv.ROM_BASE))
                if value is None or value[0] != "c":
                    state.events.append(("mask_nonconstant", repr(value), at + iv.ROM_BASE))
        elif self.getter_target is None or target == self.getter_target:
            self.getter_target = target
            field = args[1]
            result = ("s", f"get:{field[1]}" if field[0] == "c" else f"get:?@{at + iv.ROM_BASE:08X}", 0)
        elif self.difficulty_target is None:
            self.difficulty_target = target
            result = ("s", "difficulty", 0)
            state.dom["difficulty"] = Domain(0, self.difficulties - 1)
        state.r[0] = result
        state.r[1] = state.r[2] = state.r[3] = UNKNOWN
        state.r[12] = UNKNOWN
        state.cmp = None

    def step_until_fork(self, pc, state, max_steps):
        while True:
            state.steps += 1
            if state.steps > max_steps:
                state.events.append(("step_limit", pc + iv.ROM_BASE))
                self.paths.append(state)
                return []
            if pc in self.loop_exits:
                pc = self.loop_exits[pc]
                continue
            if not self.in_span(pc):
                state.events.append(("left_span", pc + iv.ROM_BASE))
                self.paths.append(state)
                return []
            instruction = decode(self.data, pc)
            mnemonic = instruction.mnemonic
            following = pc + instruction.size
            if mnemonic == "bl":
                target = instruction.target
                if self.in_span(target):
                    pc = target
                    continue
                absolute = target + iv.ROM_BASE
                trampoline = decode(self.data, target)
                if trampoline.mnemonic == "bx":
                    value = self.resolve(state, state.r[trampoline.rm])
                    if value[0] != "c":
                        state.events.append(("indirect_unknown", pc + iv.ROM_BASE))
                        self.paths.append(state)
                        return []
                    absolute = value[1] & ~1
                helper = absolute - iv.ROM_BASE
                entry = self.case_entry(helper)
                if entry is not None:
                    return self.case(state, pc, entry)
                self.call(state, pc, absolute)
                pc = following
                continue
            if mnemonic == "b":
                if instruction.condition is None:
                    pc = instruction.target
                    continue
                return self.cond_fork(state, instruction.condition, instruction.target, following)
            if mnemonic == "pop" and 15 in instruction.registers or mnemonic == "bx":
                self.paths.append(state)
                return []
            self.exec(state, instruction)
            pc = following

    def exec(self, state, instruction):
        mnemonic = instruction.mnemonic
        registers = state.r

        def resolved(index):
            return self.resolve(state, registers[index])

        if mnemonic == "push":
            for register in reversed(instruction.registers):
                state.sp -= 4
                state.stack[state.sp] = registers[register]
            registers[13] = ("p", "sp", state.sp)
            return
        if mnemonic == "pop":
            for register in instruction.registers:
                registers[register] = state.stack.get(state.sp, UNKNOWN)
                state.sp += 4
            registers[13] = ("p", "sp", state.sp)
            return
        if mnemonic == "ldr" and instruction.literal is not None:
            registers[instruction.rd] = constant(self.literal(instruction.literal))
            return
        if mnemonic in ("ldr", "ldrh", "ldrb", "ldrsh", "ldrsb"):
            base = resolved(instruction.rn) if instruction.rn != 13 else ("p", "sp", state.sp)
            offset = constant(instruction.immediate) if instruction.immediate is not None else resolved(instruction.rm)
            address = symbolic_add(base, offset)
            if address[0] == "p" and address[1] == "sp":
                registers[instruction.rd] = state.stack.get(address[2], UNKNOWN) if mnemonic == "ldr" else UNKNOWN
            elif address[0] == "p" and address[1] == "mon":
                registers[instruction.rd] = ("s", f"mon[{address[2]}:{instruction.width}]", 0)
            elif address[0] == "c" and iv.ROM_BASE <= address[1] < iv.ROM_BASE + len(self.data):
                at = address[1] - iv.ROM_BASE
                value = int.from_bytes(self.data[at:at + instruction.width], "little")
                if mnemonic == "ldrsh" and value & 0x8000:
                    value -= 0x10000
                if mnemonic == "ldrsb" and value & 0x80:
                    value -= 0x100
                registers[instruction.rd] = constant(value)
            else:
                registers[instruction.rd] = ("s", f"load:{repr(address)}@{instruction.address + iv.ROM_BASE:08X}", 0) \
                    if address[0] != "u" else UNKNOWN
            return
        if mnemonic in ("str", "strh", "strb"):
            base = resolved(instruction.rn) if instruction.rn != 13 else ("p", "sp", state.sp)
            offset = constant(instruction.immediate) if instruction.immediate is not None else resolved(instruction.rm)
            address = symbolic_add(base, offset)
            value = resolved(instruction.rd)
            if address[0] == "p" and address[1] == "sp":
                state.stack[address[2]] = value
            return
        if mnemonic in ("stmia", "ldmia"):
            if mnemonic == "ldmia":
                for register in instruction.registers:
                    registers[register] = UNKNOWN
            return
        if mnemonic == "mov":
            if instruction.rm is not None:
                registers[instruction.rd] = registers[instruction.rm] if instruction.rm != 13 else ("p", "sp", state.sp)
            else:
                registers[instruction.rd] = constant(instruction.immediate)
                state.cmp = ("cmp", registers[instruction.rd], constant(0))
            return
        if mnemonic == "add" and instruction.rn == 13 and instruction.rd == 13:
            state.sp += instruction.immediate
            registers[13] = ("p", "sp", state.sp)
            return
        if mnemonic == "sub" and instruction.rn == 13 and instruction.rd == 13:
            state.sp -= instruction.immediate
            registers[13] = ("p", "sp", state.sp)
            return
        if mnemonic == "add" and instruction.rn == 13:
            registers[instruction.rd] = ("p", "sp", state.sp + instruction.immediate)
            return
        if mnemonic == "add" and instruction.rn == 15:
            registers[instruction.rd] = constant(((instruction.address + 4) & ~3) + instruction.immediate + iv.ROM_BASE)
            return
        if mnemonic in ("add", "sub"):
            left = resolved(instruction.rn) if instruction.rn is not None else resolved(instruction.rd)
            if instruction.rn == 13:
                left = ("p", "sp", state.sp)
            right = constant(instruction.immediate) if instruction.immediate is not None else (
                resolved(instruction.rm) if instruction.rm != 13 else ("p", "sp", state.sp))
            if mnemonic == "add":
                value = symbolic_add(left, right)
            elif right[0] == "c":
                value = symbolic_add(left, constant(-right[1]))
            else:
                value = UNKNOWN
            if mnemonic == "sub" and left[0] == right[0] == "s" and left[1] == right[1]:
                value = constant(left[2] - right[2])
            registers[instruction.rd] = value
            state.cmp = ("cmp", left, right) if mnemonic == "sub" and right[0] == "c" else ("cmp", value, constant(0))
            return
        if mnemonic == "cmp":
            left = resolved(instruction.rn)
            right = constant(instruction.immediate) if instruction.immediate is not None else resolved(instruction.rm)
            state.cmp = ("cmp", left, right)
            state.carry = left[1] >= right[1] if left[0] == right[0] == "c" else None
            return
        if mnemonic == "cmn":
            state.cmp = None
            return
        if mnemonic == "tst":
            left, right = resolved(instruction.rn), resolved(instruction.rm)
            state.cmp = ("tst", constant(left[1] & right[1]), None) if left[0] == right[0] == "c" else (
                "tst", ("s", f"bit:{repr(left)}&{repr(right)}", 0), None)
            return
        if mnemonic in ("lsl", "lsr", "asr"):
            value = resolved(instruction.rn)
            shift = instruction.immediate
            if value[0] == "c":
                if mnemonic == "lsl":
                    result = (value[1] << shift) & MASK32
                elif mnemonic == "lsr":
                    result = value[1] >> shift if shift < 32 else 0
                else:
                    signed = value[1] - (1 << 32) if value[1] & 0x80000000 else value[1]
                    result = (signed >> min(shift, 31)) & MASK32
                registers[instruction.rd] = constant(result)
                state.cmp = ("cmp", constant(result), constant(0))
            elif shift == 0 and mnemonic == "lsl":
                registers[instruction.rd] = value
                state.cmp = ("cmp", value, constant(0))
            elif value[0] == "s" and (mnemonic == "lsl" and shift in (16, 24)
                                      or mnemonic in ("lsr", "asr") and shift in (16, 24)):
                registers[instruction.rd] = value
                state.cmp = ("cmp", value, constant(0))
            elif value[0] == "s" and mnemonic == "lsl" and shift == 31:
                registers[instruction.rd] = ("s", f"bit0:{value[1]}", 0)
                state.cmp = ("tst", registers[instruction.rd], None)
            else:
                registers[instruction.rd] = UNKNOWN
                state.cmp = None
            return
        if mnemonic in ("sbc", "adc") and state.carry is not None:
            left, right = resolved(instruction.rd), resolved(instruction.rm)
            if left[0] == right[0] == "c":
                carry = 1 if state.carry else 0
                result = left[1] - right[1] - (1 - carry) if mnemonic == "sbc" else left[1] + right[1] + carry
                registers[instruction.rd] = constant(result)
                state.cmp = ("cmp", constant(result), constant(0))
                return
        if mnemonic in ("and", "orr", "eor", "bic", "mul", "neg", "mvn", "adc", "sbc", "ror"):
            left, right = resolved(instruction.rd), resolved(instruction.rm)
            if left[0] == right[0] == "c":
                x, y = left[1], right[1]
                result = {"and": x & y, "orr": x | y, "eor": x ^ y, "bic": x & ~y, "mul": x * y,
                          "neg": -y, "mvn": ~y}.get(mnemonic)
                if result is None:
                    registers[instruction.rd] = UNKNOWN
                    state.cmp = None
                    return
                registers[instruction.rd] = constant(result)
                state.cmp = ("cmp", constant(result), constant(0))
            elif mnemonic == "neg" and right[0] == "s":
                registers[instruction.rd] = ("s", f"neg:{right[1]}:{right[2]}", 0)
                state.cmp = None
            else:
                registers[instruction.rd] = ("s", f"{mnemonic}:{repr(left)}:{repr(right)}"
                                             f"@{instruction.address + iv.ROM_BASE:08X}", 0) \
                    if mnemonic in ("and", "orr") else UNKNOWN
                state.cmp = None
            return
        if mnemonic in ("undefined", "swi"):
            state.events.append(("unhandled", mnemonic, instruction.address + iv.ROM_BASE))
            return
        state.events.append(("unhandled", mnemonic, instruction.address + iv.ROM_BASE))


def declared_mask_map(block):
    stage = next(stage for stage in block["stages"] if stage["operation"] == "packed_masks")
    result = {}
    for rule in stage["rules"]:
        species = rule["species"] if rule["species"] == "any" else rule["species"]
        for selected in species if isinstance(species, list) else [species]:
            for difficulty in rule["difficulties"]:
                result[rule["trainer"], selected, difficulty] = {rule["packed"]}
    return result


def covers_all_species(domains):
    parts = sorted(part for domain in domains for part in domain.parts)
    merged = []
    for lo, hi in parts:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged == [(0, 0xFFFF)]


def recomputed_mask_map(block, paths):
    wildcards = {rule["trainer"] for rule in next(
        stage for stage in block["stages"] if stage["operation"] == "packed_masks")["rules"]
        if rule["species"] == "any"}
    result = {}
    wildcard_writes = {}
    for path in paths:
        trainer = path.dom["trainer"].single()
        species = path.dom.get("get:11", Domain())
        difficulty = path.dom.get("difficulty", Domain(0, len(block["difficulties"]) - 1))
        for event in (event for event in path.events if event[0] == "mask"):
            packed = event[2][1]
            if trainer in wildcards:
                for day in range(len(block["difficulties"])):
                    if not difficulty.keep(day, day).empty():
                        wildcard_writes.setdefault((trainer, day), []).append((species, packed))
                continue
            selected_species = species.single()
            if trainer is None or selected_species is None:
                raise ValueError("packed mask path has an unresolved trainer or species")
            for day in range(len(block["difficulties"])):
                if not difficulty.keep(day, day).empty():
                    result.setdefault((trainer, selected_species, day), set()).add(packed)
    for (trainer, day), writes in wildcard_writes.items():
        if len({packed for _, packed in writes}) == 1 and covers_all_species([species for species, _ in writes]):
            result[trainer, "any", day] = {writes[0][1]}
    return result


@needs_rom
class RomMaskWalkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = Profile.by_name("unbound-2.1.1.1")
        cls.block = cls.profile["pokedex"]["trainers"]["ivs"]
        cls.data = cls.profile.load_rom(rom_path()).data
        cls.paths = MaskWalk(cls.block, cls.data).run()

    def test_declared_masks_equal_the_symbolic_rom_walk(self):
        problems = [(index, event) for index, path in enumerate(self.paths)
                    for event in path.events if event[0] in MaskWalk.BAD_EVENTS]
        self.assertEqual(problems, [])
        self.assertEqual(recomputed_mask_map(self.block, self.paths), declared_mask_map(self.block))
