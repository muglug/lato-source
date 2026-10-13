"""Naming for the modified families; original authorship/licensing is retained."""
import re

FAMILY_NAME_IDS = {1, 3, 4, 6, 16, 18, 20, 21, 25}


def modified_name(value):
    return re.sub(r'\b(Lato|Carlito)(?!26)', lambda m: m[1]+'26', value)


def rename_font(font):
    for record in font['name'].names:
        if record.nameID in FAMILY_NAME_IDS:
            record.string = modified_name(record.toUnicode()).encode(record.getEncoding())
    if 'CFF ' in font:
        cff = font['CFF '].cff
        cff.fontNames = [modified_name(name) for name in cff.fontNames]
        for top in cff.topDictIndex:
            for key in ('FamilyName', 'FullName', 'FontName'):
                value = getattr(top, key, None)
                if value is not None:
                    setattr(top, key, modified_name(value))


def original_path(path):
    """Locate the equivalent file in a pre-rename build snapshot."""
    return type(path)(str(path).replace('Lato26-', 'Lato-')
                      .replace('Lato26.~VF', 'Lato.~VF')
                      .replace('Carlito26', 'Carlito'))
