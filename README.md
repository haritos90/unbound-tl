# unbound-tl - a translation project of the Pokemon Unbound ROM hack 2.1.1.1, built as a patch for the Unbound ROM

**English** | [Русский](README_ru.md)

> [!IMPORTANT]
> This is not an official project. It is not supported by Skeli and the Pokemon Unbound team and is not affiliated with them.
>
> Patching a ROM may affect the experience of the game.

What a translation changes:

- the texts of the game and the pointers to them;
- the glyphs of the fonts and the pictures that contain text;
- the keyboards for names and chat and the order of the chat words, which follow the alphabet of the language;
- no gameplay: the story, the battles, the save files and link play work as in the original;
- no game code changes, other than 2 exceptions:
  - A language that uses metric units prints the height and weight of the Pokédex page in metres and kilograms. Two drawing routines are replaced; the stored values, which moves such as Low Kick read, stay as they are.
  - The DexNav display draws names from a picture font. Its letter lookup is replaced so that the letters of the language can be drawn.

A released translation is applied with the [patcher](https://haritos90.github.io/gen3tl/patch) of the gen3tl website. The original ROM is not distributed here.

## Contribute to a translation

Translations are edited and submitted in the [translation editor](https://haritos90.github.io/gen3tl/editor), which works through a web browser (all work stays local until submitted). [CONTRIBUTING.md](CONTRIBUTING.md) describes the steps.

## Add a language

Open an issue in this repository and name the language, or open a pull request that adds the folder of the language ([CONTRIBUTING.md](CONTRIBUTING.md#add-a-language)).

## How languages are stored

Each language has one folder, `translation/<code>/`, named by its language code.

| Path in the folder | Content |
| --- | --- |
| `po/` | the translated texts, as gettext PO files grouped by the part of the game |
| `pokedex-labels.po` | the labels of the Pokédex pages |
| `glossary.tsv` | the terms of the game and their translations |
| `policy.toml` | the settings of the language, such as its naming keyboard |
| `release.toml` | the release state of the language |
| `graphics/` | the translated pictures |

- A PO entry holds the key of a text and its translation. The text in the original language is not stored: the editor reads it from the ROM.
- A new language starts with the PO files, `policy.toml` and `release.toml`; the other files are added as the translation grows.

## Add a game

This project covers one game. To add another game to gen3tl, open an issue in the [gen3tl repository](https://github.com/haritos90/gen3tl/issues).

## Credits

- Pokémon Unbound is a ROM hack by Skeli Games; the game's own credits name its team.
- Pokémon and its names and characters belong to Nintendo, Game Freak and The Pokémon Company.
- Contributors: as the Git history of this repository records them.

## License

| Files | License | Text |
| --- | --- | --- |
| the files outside `.github/`: the translations, glossaries, graphics edits and documents | Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0) | [LICENSE](LICENSE) |
| the files under `.github/`: the workflows, the issue form and the scripts | the MIT License of the toolkit | [.github/LICENSE](.github/LICENSE) |

CC BY-SA 4.0 allows sharing and adapting the work with credit; adaptations are shared under the same license.
