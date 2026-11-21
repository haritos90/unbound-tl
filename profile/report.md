# Discovery report: unbound-2.1.1.1

| Item | Value |
|---|---|
| Generated profile | `profile.toml` |
| Inputs | base ROM, family files, optional ROM-matched inventory |
| Overlay coverage | `gen3tl discover check` |

| Kind | Verified | Candidate | Omitted | Unresolved |
|---|---|---|---|---|
| identity | 2 | 0 | 0 | 0 |
| family | 1 | 0 | 0 | 0 |
| font | 5 | 1 | 0 | 0 |
| table | 162 | 1 | 1 | 0 |
| pointer-table | 0 | 0 | 0 | 1 |
| string | 1 | 1 | 0 | 1 |
| reference | 97 | 0 | 0 | 1 |
| script-command | 1 | 2 | 0 | 7 |
| map | 5 | 0 | 0 | 0 |
| window | 575 | 0 | 0 | 0 |
| keyboard | 1 | 0 | 0 | 0 |
| save | 50 | 0 | 0 | 0 |
| sprite-table | 0 | 0 | 0 | 0 |
| graphic | 0 | 0 | 0 | 0 |
| code | 0 | 0 | 0 | 0 |
| reach | 0 | 0 | 0 | 3 |
| context | 4 | 0 | 0 | 6 |
| project | 0 | 0 | 0 | 0 |
| unclassified | 0 | 0 | 0 | 0 |

## Candidates

| Fact | Kind | Statement |
|---|---|---|
| `script.command[92]` | script-command | unresolved helper call at 0x6c2ca targets 0x80228: unproved jump table bounds at 0x9ff0b4; unresolved helper call at 0x6c2ca targets 0x80228: unresolved helper call at 0x9ff0e8 targets 0x80168: helper control flow leaves bounded code at 0x801e4; unresolved helper call at 0x6c2ca targets 0x80228: unresolved helper call at 0x9ff0fa targets 0x80168: helper control flow leaves bounded code at 0x801da; cfru-trainerbattle: variable operand layouts are not inferred |
| `script.command[182]` | script-command | repeated-stream-advance: variable operand layouts are not inferred |
| `font_slots` | font | Provided ROM-matched inventory only, including unverified entries; not whole-ROM coverage. |
| `table[name=types_short]` | table | The anchored short-name copy has no confirmed linked indexed reader; live use remains unproved. |
| `text_prefixes[name=berry-number-prefix]` | string | A literal prefix reaches StringAppend after StringCopy initializes the same buffer; the formatter continuation and presentation limits remain unproven. |

## Omitted

| Fact | Kind | Statement |
|---|---|---|
| `pokedex.sources.trades` | table | Native trade table loads are not reachable from the reader entry. The reader entry redirects before all declared table loads; retained records have no confirmed live reader. |

## Unresolved

| Fact | Kind | Statement |
|---|---|---|
| `script.command[12]` | script-command | unresolved helper call at 0x6a24e targets 0x698d0: next script pointer is opaque at 0x698d0 |
| `script.command[94]` | script-command | exit has unknown script pointer at 0x6c2f4; next script pointer is opaque at 0x6c2ec |
| `script.command[95]` | script-command | exit has unknown script pointer at 0x6c308; next script pointer is opaque at 0x6c300 |
| `script.command[120]` | script-command | handler state limit reached at 0x1ec271c; stream offset 4 |
| `script.command[126]` | script-command | unresolved helper call at 0x6bcda targets 0xcacfc: helper state limit reached at 0xcacfc |
| `script.command[171]` | script-command | unresolved helper call at 0x6b6d2 targets 0x69058: unresolved helper call at 0x69062 targets 0x6900c: helper state limit reached at 0x6900c |
| `script.command[207]` | script-command | unresolved helper call at 0x6a2a4 targets 0x698d0: next script pointer is opaque at 0x698d0 |
| `text_prefixes[name=berry-number-prefix]` | string | The prefix source and shared destination are proven. The formatter redirects before number and item-name concatenation; the continuation needs register-state and source-table proofs. Row capacity, font advances, quantity placement and post-omission limits need independent consumer evidence; runtime fit observations remain manual. |
| `context.speaker_colours` | context | The text bytes expose palette indices, not semantic gender labels. A family dialogue-colour convention or independent labelled speaker evidence is required. |
| `context.textcolor_genders` | context | The textcolor command exposes a colour selector. Mapping its values to gender requires an independently established dialogue convention. |
| `context.sprite_genders` | context | Map and trainer facts link individual uses, but a sprite can be reused. A consistent identity domain or independent sprite-gender evidence is required before assigning a global hint. |
| `context.participants` | context | Speaker/addressee relationships across scenes and natural-language gender assertions are not encoded as script identities. Runtime continuity and reviewed text interpretation remain manual. |
| `context.record_speakers` | context | The record reader must prove each text field, table extent, class byte and gender byte, including the gender-value convention. Pointer-table shape alone does not establish those meanings. |
| `reach.default_origin` | reach | Map banks identify current structures, not the historical provenance label of every remaining ROM byte. An origin convention is required. |
| `reach.origin_regions` | reach | Current map and function facts do not encode historical allocation boundaries. A verified base-image comparison or provenance manifest is required. |
| `reach.table` | pointer-table | The retained table borders neighbouring window and animation data and its original getters redirect elsewhere. An independent root, record extent and text-field proof is required. |
| `reach.unused_entries` | reach | Absence from walked script selections does not prove a native special entry unused. A complete direct and computed dispatch-domain proof is required. |
| `coverage.unread_reference` | reference | Unselected menu rows need the complete native selector domain; apparent sample-data pointers need audio extent and consumer evidence. Pointer shape and absent map-script uses are insufficient. |
| `context.native_fill[name=table-1FB2DF8]` | context | A unique indexed text pointer must reach a known string-buffer copy. The handler combines a selector loop with conditional suffix writes; reproduction requires a joined buffer-state proof, including the selector-table row and every append branch. |

## Runtime samples

| Item | Value |
|---|---|
| Compared bytes | size and SHA-256 |
| Raw predictions | `gen3tl rom evidence --sample` |
| Tier raised by | discriminating samples |
| Coverage | the listed samples |

| Fact | Shot | Compared bytes | SHA-256 | Non-background pixels | Result | Tier raised | Shared facts |
|---|---|---:|---|---:|---|---|---|
| `keyboard.table[name=keys]` | `isolated-a` | 1 | `cdce9374e0fecee1655cbc7207b0ed392201941f084c4b5672e917a99c7b2b26` | n/a | discriminating | ingame | none |
| `font[name=font0]` | `page-others` | 768 | `bdeaacc3b821f3f19895f242a05ab90843c6207004791cef2fcf0820ac3e0cf9` | 36 | shared | none | `font[name=font1]`, `font[name=font2]`, `font[name=font3]` |
| `font[name=font1]` | `page-others` | 768 | `bdeaacc3b821f3f19895f242a05ab90843c6207004791cef2fcf0820ac3e0cf9` | 36 | shared | none | `font[name=font0]`, `font[name=font2]`, `font[name=font3]` |
| `font[name=font2]` | `page-others` | 768 | `bdeaacc3b821f3f19895f242a05ab90843c6207004791cef2fcf0820ac3e0cf9` | 36 | shared | none | `font[name=font0]`, `font[name=font1]`, `font[name=font3]` |
| `font[name=font3]` | `page-others` | 768 | `bdeaacc3b821f3f19895f242a05ab90843c6207004791cef2fcf0820ac3e0cf9` | 36 | shared | none | `font[name=font0]`, `font[name=font1]`, `font[name=font2]` |
| `keyboard.table[name=columns]` | `page-others` | 1 | `beead77994cf573341ec17b58bbf7eb34d2711c993c1d976b128b3188dc1829a` | n/a | discriminating | ingame | none |
| `keyboard.table[name=page_keyboard]` | `page-others` | 1 | `dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986` | n/a | shared | none | `keyboard.table[name=label_subsprites]` |
| `keyboard.table[name=next_keyboard]` | `page-others` | 1 | `4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a` | n/a | shared | none | `keyboard.table[name=label_palette]` |
| `keyboard.table[name=next_label]` | `page-others` | 1 | `6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d` | n/a | shared | none | `keyboard.table[name=column_x]` |
| `font[name=small]` | `continue` | 768 | `b1410a1b7f64d250653c975da7300ccc0f173a927a4aa1d37318082d39fed061` | 19 | shared | none | `font[name=font0]`, `font[name=font1]`, `font[name=font2]`, `font[name=font3]` |
| `table[name=species]` | `summary-3-detail` | 10 | `be038f309acab4ef917807dab385cdb93aa589b3fcb9f26db33ff8c099b99a45` | n/a | discriminating | ingame | none |
| `table[name=moves]` | `summary-3-detail` | 7 | `f0615b474167c0ec2df1482eb61ed00f1ac79cc7a7ff62011aafb23485e83dc4` | n/a | discriminating | ingame | none |
| `table[name=abilities]` | `summary-3-detail` | 9 | `3306818a9c934dd338ec49c564dc21b17d0fc379df50479c5939957694d20fd0` | n/a | discriminating | ingame | none |
| `table[name=items]` | `item-direct` | 14 | `806c2d20412d04adfa47ffdb2486c33edba8819bb24ee62a59a804c284208ed9` | n/a | discriminating | ingame | none |
| `table[name=item_plural_s]` | `normal-ordinary` | 1 | `d0752b60adb148ca0b3b4d2591874e2dabd346373e731c27463d65b449cc234c` | n/a | shared | none | `table[name=count_plural_s]`, `table[name=egg_count_plural_s]`, `table[name=item_plural_s_trade]` |
| `table[name=item_plural_lower]` | `normal-lower` | 1 | `2795044ce0f83f718bc79c5f2add1e52521978df91ce9b7f82c9097191d33602` | n/a | shared | none | `table[name=item_plural_lower_trade]` |
| `table[name=item_plural_upper]` | `normal-upper` | 1 | `ae3f4619b0413d70d3004b9131c3752153074e45725be13b9a148978895e359e` | n/a | shared | none | `table[name=item_plural_upper_trade]` |
| `table[name=berry_blender_possessive]` | `berry-full` | 4 | `62e8e83163c5b2e701c1722ea848b28619a965ac333df678415a72f8a974f9d1` | n/a | discriminating | ingame | none |
| `table[name=berry_blender_apostrophe]` | `berry-direct` | 1 | `27952171c7fcdf0ddc765ab4f4e1c537cb29e5e533d57b3456257ee785c81711` | n/a | shared | none | `table[name=ability_popup_possessive]` |
| `table[name=trainer_names]` | `battle-action` | 5 | `8cf232957f1bdcd1cf216d2535252f6fbd98f6cff517bf0761f379bc50d719c4` | n/a | discriminating | ingame | none |

## Named residue

| Item | Value |
|---|---|
| Acknowledged unresolved facts | 19 |
| New unresolved facts | 0 |
| Effect of an acknowledgement on coverage | none |

## Structural discovery

| Item | Value |
|---|---|
| Scope | discovered ROM bindings and layouts |
| Whole-ROM coverage | unverified |

| Section | Verified | Candidate | Omitted | Unresolved |
|---|---:|---:|---:|---:|
| `keyboard.table` | 14 | 0 | 0 | 0 |
| `pokedex.abilities` | 2 | 0 | 0 | 0 |
| `pokedex.dex` | 6 | 0 | 0 | 0 |
| `pokedex.encounters` | 12 | 0 | 0 | 0 |
| `pokedex.evolution` | 6 | 0 | 0 | 0 |
| `pokedex.growth_rates` | 1 | 0 | 0 | 0 |
| `pokedex.icons` | 2 | 0 | 0 | 0 |
| `pokedex.items` | 10 | 0 | 0 | 0 |
| `pokedex.learnsets` | 4 | 0 | 0 | 0 |
| `pokedex.map_sections` | 1 | 0 | 0 | 0 |
| `pokedex.maps` | 1 | 0 | 0 | 0 |
| `pokedex.moves` | 30 | 0 | 0 | 0 |
| `pokedex.sources` | 1 | 0 | 1 | 0 |
| `pokedex.species` | 19 | 0 | 0 | 0 |
| `pokedex.sprites` | 4 | 0 | 0 | 0 |
| `pokedex.trainers` | 21 | 0 | 0 | 0 |
| `pokedex.type_effectiveness` | 1 | 0 | 0 | 0 |
| `pokedex.type_icons` | 1 | 0 | 0 | 0 |
| `strings.pointer_table` | 3 | 0 | 0 | 0 |
| `table` | 23 | 1 | 0 | 0 |

## Family evidence

| Family | Fingerprints | Selected | Header valid | Categories |
|---|---:|---|---|---|
| `firered-cfru` | 10/10 (100%) | true | true | extension, naming, renderer, script, width |

### `firered-cfru`

| Function | Addresses |
|---|---|
| `small-renderer` | `0x6448` |
| `normal-copy-renderer` | `0x64f0` |
| `normal-renderer` | `0x65b8`, `0x67ec`, `0x6958` |
| `simple-width` | `0x64d0`, `0x6598` |
| `copy-width` | `0x67cc` |
| `normal-width` | `0x66f8`, `0x692c`, `0x6a98` |
| `script-halfword` | `0x698f8` |
| `script-word` | `0x69910` |
| `naming-cycle` | `0x9e294` |
| `hidden-ability` | `0xa13f54` |

## Codec and controls

| Item | Value |
|---|---|
| Selected codec | `gen3-western` |
| Control contract | `gen3-frlg` |
| Selection | family anchors |
| Unobserved and custom controls | unverified |

| Candidate | Text anchors | Control anchors | Score |
|---|---:|---:|---:|
| `gen3-western` | 7 | 2 | 9 |
| `ascii` | 0 | 0 | 0 |

## Verified font bindings

| Font | Glyphs | Widths | Count | Format | Printer IDs |
|---|---|---|---:|---|---|
| `font0` | `0x1f3100` | `0x1fb100` | 512 | `16x16` | [1] |
| `font1` | `0x1ff300` | `0x207300` | 512 | `16x16` | [2, 3] |
| `font2` | `0x20f618` | `0x217618` | 512 | `16x16` | [4] |
| `font3` | `0x21f930` | `0x227930` | 512 | `16x16` | [5] |
| `small` | `0x1eaf00` | `0x1eef00` | 512 | `8x16` | [0] |

## Script commands

| Item | Value |
|---|---|
| Command table | `0x15f9b4`-`0x15fd08` |
| Initializer | `0x69a80` |
| Dispatcher | `0x69804` |
| Handlers | 213 |
| Fixed | 22 |
| Variable | 2 |
| Unresolved | 7 |
| Handler evidence and compatibility comparisons | discovery metadata |

## Character slots

| Item | Value |
|---|---|
| Status | candidate |
| Scope | supplied ROM-matched inventory, unverified entries included |
| Whole-ROM allocation | unverified |
| Inventory entries | 26155 |
| Inventory digest | `afbdb03b6c11824639b68c654d648c6ac34fdadfb92e4d0798269bcd1538ede7` |
| Scoped free bytes | `18` `1F` `2F` `30` `31` `32` `33` `37` `38` `3A` `3B` `3C` `3D` `3E` `3F` `40` `41` `42` `43` `44` `45` `46` `47` `48` `49` `4A` `4B` `4C` `4D` `4E` `4F` `50` `5E` `5F` `60` `61` `62` `65` `66` `67` `69` `6A` `6B` `6C` `6D` `6E` `70` `72` `73` `74` `75` `76` `77` `78` `7D` `7E` `7F` `80` `81` `82` `83` `87` `88` `89` `8A` `8B` `8C` `8D` `8E` `8F` `90` `91` `92` `93` `94` `96` `97` `98` `99` `9A` `9B` `9C` `9D` `9E` `9F` |

| Candidates | Used | Blank in every font | Scoped free |
|---:|---:|---:|---:|
| 91 | 6 | 91 | 85 |
