# Runtime observations

Values read from the running original ROM that confirm facts of the profile.

## Files

| File | Content |
| --- | --- |
| `samples.json` | the sample plan: 20 samples, each with its fact, its scenario and the read to take |
| `observations.json` | the record: per sample the fact, the predicted and the observed value as byte count and SHA-256, the scenario and the digests of its inputs |
| `scenarios/` | the seven scenarios the samples run |

## Commands

| Command | Use | Needs |
| --- | --- | --- |
| `gen3tl discover run`, `gen3tl discover regenerate` | compare the predictions of the profile with the record | the original ROM |
| `gen3tl discover observe` | take the samples again and write a record | the original ROM, a headless emulator core, the inputs below |

## Inputs outside the repository

| Scenario | Input |
| --- | --- |
| `naming-isolated.txt` | `verify/states/e1.state` |
| `battle-samples.txt`, `plural-samples-2.txt`, `script-samples-3.txt`, `suffix-simple.txt` | `verify/states/e6.state` |
| `save-ui.txt`, `suffix-simple-2.txt` | `verify/fixtures/observations.sav` |

## Facts of the record

| Fact | Value |
| --- | --- |
| Samples that confirm one fact alone | 8: six name tables, two keyboard tables |
| Samples shared by several facts | 12, the five font samples among them |
| Identity of an input | its size and SHA-256 under `scenario.inputs`; a repeat needs the same bytes |
| Emulator core of the record | headless mGBA libretro core, SHA-256 `4c6f47e7617403e1c1dee5d0604e512315c07eedff34eb1bc57ae090f9d6a7dd` |
