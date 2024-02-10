import click
import pyscreenshot as ImageGrab
import pygetwindow as gw
import numpy as np
import easyocr
import urllib.request, json
import itertools

AK_OPERATOR_SOURCE = "https://aceship.github.io/AN-EN-Tags/json/tl-akhr.json"
AK_TYPE_SOURCE = "https://aceship.github.io/AN-EN-Tags/json/tl-type.json"
AK_TAGS_SOURCE = "https://aceship.github.io/AN-EN-Tags/json/tl-tags.json"

CN_CLASS_SUFFIX = "干员"

TOP_OPERATOR = "高级资深干员"
PRIORITY_TAGS = ["支援机械", "资深干员", TOP_OPERATOR]
MISSPELL_TABLE = [
    ("D-Recovery", "DP-Recovery"),
    ("DP_Recovery", "DP-Recovery"),
    ("AOE", "AoE"),
    ("Crowd-Control", "Crowd Control"),
]

LANG_SETS = {
    "en": ["en"],
    "cn": ["ch_sim"],
    "jp": ["jp"],
    "kr": ["kr"],
}

INDENT_LEVEL = "  "


@click.command()
@click.option('--lang', default="en", help="Language model to load, like 'en' or 'cn'")
@click.option('--window', required=True, prompt="Provide emulator window title", help="Title of the emulator window to read and interact with")
@click.option('--verbose', default=False, help="Print extra information for debugging")
def main (lang: str, window: str, verbose: bool):       
    # Load operator data from Aceship
    with urllib.request.urlopen(AK_OPERATOR_SOURCE) as data:
        ak_operators = json.load(data)
    with urllib.request.urlopen(AK_TAGS_SOURCE) as data:
        ak_tags = json.load(data)
        ak_tags_index = [t[f"tag_{lang}"] for t in ak_tags]
    with urllib.request.urlopen(AK_TYPE_SOURCE) as data:
        ak_classes = json.load(data)
        ak_classes_index = [c[f"type_{lang}"] for c in ak_classes]
        
    # Load OCR language model
    click.echo(f"Loading model for '{lang}'...")
    reader = easyocr.Reader(LANG_SETS[lang], gpu = True)

    should_exit = False
    while not should_exit:
        # Get by either window title, active window or window directly
        windows = [w for w in gw.getAllWindows() if w.title == window]
        target = None

        if windows:
            target = windows[0]
            click.echo(f"Matched window: {target} (matches: {len(windows)})")
        else:
            click.echo(f"No direct match, looking for similarly named windows...")
            windows = gw.getWindowsWithTitle(window)
            if windows:
                if len(windows) == 1:
                    target = windows[0]
                    click.echo(f"Found one matching window with similar title '{windows[0].title}', proceeding...")
                else:
                    click.echo(f"Found multiple potential windows: {[w.name for w in windows]}. Try a more precise name! Exiting...")
                    return 1
            else:
                click.echo(f"No windows were found for the title '{window}'. Exiting...")
                return 1

        # Take screenshot of the window
        bounds_x = np.sort([int(np.abs(target.left)), int(np.abs(target.right))])
        bounds_y = np.sort([int(np.abs(target.top)), int(np.abs(target.bottom))])

        im = ImageGrab.grab(bbox=(bounds_x[0], bounds_y[0], bounds_x[1], bounds_y[1]))

        # Read with OCR
        result = reader.readtext(np.array(im))

        # Prepare collection arrays
        classes: list = []
        tags: list = []
        # ->
        operator_combos: dict[set, list] = {}

        # Helper methods
        def _print_hinted_class_or_tag(tag, highlight=False, nl=True, ljust=12, rpad=2):
            matching_classes = [c for c in ak_classes if c[f'type_{lang}'] == tag or c["type_cn"] == tag]
            matching_tags = [t for t in ak_tags if t[f'tag_{lang}'] == tag or t["tag_cn"] == tag]

            result = dict(kind="class" if matching_classes else "tag")

            if result["kind"] == "class":
                for key, value in matching_classes[0].items():
                    result[key.removeprefix("type_")] = value
            elif result["kind"] == "tag":
                for key, value in matching_tags[0].items():
                    result[key.removeprefix("tag_")] = value

            text_result = result[lang] if lang == "en" else f"{result[lang]} ({result['en']})"

            if ljust:
                text = f"{text_result.ljust(ljust, '　')}"
            else:
                text = text_result

            color = "cyan" if matching_classes else "green"
            click.secho(
                text + rpad * " ",
                fg=color if not highlight else None,
                bg=color if highlight else None,
                nl=nl
            )

        def _register_op(op, tag_list, destination):
            if frozenset(tag_list) not in destination:
                destination[frozenset(tag_list)] = list()
            destination[frozenset(tag_list)].append(op)

        def _get_color_for_rarity(rarity: int):
            match rarity:
                case 6: 
                    return "red"
                case 5:
                    return "yellow"
                case 4:
                    return "magenta"
                case 3:
                    return "blue"
                case _:
                    return "white"

        # Present matches
        # For each detected text draw bounding box in image and print text, location
        ocr_pool = []
        i = 0
        for r in result:
            x1=min(r[0][0][0], r[0][1][0], r[0][2][0], r[0][3][0])
            x2=max(r[0][0][0], r[0][1][0], r[0][2][0], r[0][3][0])
            y1=min(r[0][0][1], r[0][1][1], r[0][2][1], r[0][3][1])
            y2=max(r[0][0][1], r[0][1][1], r[0][2][1], r[0][3][1])

            if verbose:
                click.echo(f"[OCR] Detected string: {r[1]}")
            ocr_pool.append(r)

            # Only grab terms from middle of the screen
            if x1 < im.size[0] * 0.8 and x2 > im.size[0] * 0.2 and y1 < im.size[1] * 0.8 and y2 > im.size[1] * 0.2:
                term = r[1]
                if lang == "cn" and r[1].endswith(CN_CLASS_SUFFIX) and term not in ak_tags_index:
                    term = r[1].rstrip(CN_CLASS_SUFFIX)

                for misspell in MISSPELL_TABLE:
                    if term == misspell[0]:
                        term = misspell[1]

                if term in ak_classes_index:
                    classes.append(term)
                elif term in ak_tags_index:
                    tags.append(term)
            
        # Print intermediate results
        click.echo("Classes:")
        for c in classes:
            click.echo(INDENT_LEVEL, nl=False)
            _print_hinted_class_or_tag(c)
        click.echo("\nTags:")
        for t in tags:
            click.echo(INDENT_LEVEL, nl=False)
            _print_hinted_class_or_tag(t)

        # Compute operator results
        for op in ak_operators:
            if lang == "cn":
                if op.get("hidden", None):
                    continue
            else:
                if op.get("globalHidden", None):
                    continue              

            matches = set()
                
            # Add singular classes and tags first
            for c in classes:
                c_class = c if lang == "cn" else [cl['type_cn'] for cl in ak_classes if cl[f'type_{lang}'] == c][0]
                if op["type"] == c_class:
                    matches.add(c_class)
            for t in tags:
                c_tag = t if lang == "cn" else [tag['tag_cn'] for tag in ak_tags if tag[f'tag_{lang}'] == t][0]
                if c_tag in op["tags"]:
                    matches.add(c_tag)

            # Add permutations
            for i in range(len(matches)):
                for c in itertools.combinations(matches, i + 1):
                    _register_op(op, c, operator_combos)

        # Prepare results
        final_combos = []

        for combo, ops in operator_combos.items():
            ops.sort(key=lambda x:x["level"], reverse=True)
            if TOP_OPERATOR not in combo:
                ops = [op for op in ops if op["level"] <= 5]

            ops_without_low = [op for op in ops if op["level"] >= 3]

            ops_result = ops_without_low if ops_without_low else ops

            if ops_result:
                final_combos.append(dict(
                    combo=combo,
                    ops=ops,
                    guaranteed_rarity=min(ops_result, key=lambda x:x["level"])["level"],
                    priority_tags=[p for p in PRIORITY_TAGS if p in combo]
                ))

        final_combos.sort(key=lambda x:len(x["priority_tags"]) * 10 or x["guaranteed_rarity"], reverse=True)

        # Print results
        click.echo("\nCombinations:")
        for item in final_combos:
            click.secho(INDENT_LEVEL + "★" * item["guaranteed_rarity"], fg=_get_color_for_rarity(item["guaranteed_rarity"]))
            for c in item["combo"]:
                click.echo(INDENT_LEVEL * 2, nl=False)
                _print_hinted_class_or_tag(c, highlight=c in item["priority_tags"])

            click.echo(INDENT_LEVEL * 3, nl=False)
            for op in item["ops"]:
                click.secho(f"{op['name_en']} ", fg=_get_color_for_rarity(op["level"]), nl=False)
            click.echo("\n")

        if final_combos:
            click.echo("Summary:")
            click.echo(INDENT_LEVEL + "Highest guarantee: ", nl=False)
            max_guaranteed_rarity = max(final_combos, key=lambda x:x["guaranteed_rarity"])["guaranteed_rarity"]
            click.secho(f"★" * max_guaranteed_rarity, fg=_get_color_for_rarity(max_guaranteed_rarity), nl=True)

            click.echo(INDENT_LEVEL + "Combos:")
            for item_index, item in enumerate(final_combos):
                if item["guaranteed_rarity"] == max_guaranteed_rarity:
                    click.echo(INDENT_LEVEL * 2, nl=False)
                    for combo_index, combo in enumerate(item["combo"]):
                        _print_hinted_class_or_tag(combo, combo in item["priority_tags"], nl=False, ljust=0, rpad=0)
                        if combo_index < len(item["combo"]) - 1:
                            click.echo(" + ", nl=False)
                    if item_index < len(final_combos) - 1:
                        click.echo()

            all_priority_tags = set(
                [i for items in [t for t in map(lambda x:x["priority_tags"], final_combos)] for i in items]
            )
            if all_priority_tags:
                click.echo(INDENT_LEVEL + "Priority tags found:")
                for t in all_priority_tags:
                    click.echo(INDENT_LEVEL * 2, nl=False)
                    _print_hinted_class_or_tag(t, highlight=True)
                click.echo()
            else:
                click.echo("\n")

        if len(tags) + len(classes) != 5:
            click.secho(f"Warning: Incomplete OCR reading, there are missing tags!", fg="red")
            click.echo("Full OCR output:")
            for r in ocr_pool:
                click.echo(INDENT_LEVEL + r[1])

        should_exit = input("Press ENTER to try again or type \"exit\" to exit: ") == "exit"

    return 0


if __name__ == "__main__":
    main()