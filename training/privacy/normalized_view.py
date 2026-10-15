"""Local decoding views with exact source ranges; original text is never rewritten."""
from __future__ import annotations
from dataclasses import dataclass
import codecs
import html
import json
import re
import unicodedata


@dataclass(frozen=True)
class View:
    text: str
    positions: tuple[tuple[int, int], ...]


TOKEN = re.compile(r'(?:%[0-9a-fA-F]{2})+|\\u[dD][89aAbB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|&#(?:x[0-9a-fA-F]+|\d+);|&[A-Za-z][A-Za-z0-9]+;')


def _decoded(token: str):
    if token.startswith('%'):
        decoder = codecs.getincrementaldecoder('utf-8')('strict')
        result = []
        start = 0
        try:
            for offset in range(0, len(token), 3):
                value = decoder.decode(bytes([int(token[offset+1:offset+3], 16)]))
                if value:
                    result.extend((char, start, offset+3) for char in value)
                    start = offset+3
            decoder.decode(b'', final=True)
            return result
        except UnicodeError:
            return [(char, i, i+1) for i, char in enumerate(token)]
    value = json.loads('"'+token+'"') if token.startswith('\\u') else html.unescape(token)
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        return [(char, i, i+1) for i, char in enumerate(token)]
    return [(char, 0, len(token)) for char in value]


def canonical_view(text: str) -> View:
    view = View(text, tuple((i, i+1) for i in range(len(text))))
    # Bound nested decoding. Remaining encoded data is still visible to the model.
    for _ in range(2):
        chars, positions, cursor = [], [], 0
        for match in TOKEN.finditer(view.text):
            chars.extend(view.text[cursor:match.start()])
            positions.extend(view.positions[cursor:match.start()])
            for char, start, end in _decoded(match.group()):
                chars.append(char)
                positions.append((view.positions[match.start()+start][0],
                                  view.positions[match.start()+end-1][1]))
            cursor = match.end()
        chars.extend(view.text[cursor:]); positions.extend(view.positions[cursor:])
        decoded = View(''.join(chars), tuple(positions))
        if decoded.text == view.text:
            break
        view = decoded
    chars, positions = [], []
    for char, location in zip(view.text, view.positions):
        normalized = ''.join(c for c in unicodedata.normalize('NFKD', char)
                             if unicodedata.category(c) not in {'Mn', 'Me', 'Cf'})
        if not normalized and positions:
            positions[-1] = (positions[-1][0], location[1])
        for value in normalized:
            chars.append(value); positions.append(location)
    value = ''.join(chars)
    remove = set()
    for match in re.finditer(r'(?<=[\u4e00-\u9fff0-9])\s+(?=[\u4e00-\u9fff0-9])', value):
        remove.update(range(match.start(), match.end()))
    return View(''.join(c for i,c in enumerate(chars) if i not in remove),
                tuple(p for i,p in enumerate(positions) if i not in remove))


def project(original: str, view: View, entities: list[dict]) -> list[dict]:
    result = []
    for entity in entities:
        for match in re.finditer(re.escape(entity['text']), view.text):
            start, end = view.positions[match.start()][0], view.positions[match.end()-1][1]
            item = {'text': original[start:end], 'type': entity['type']}
            if item not in result:
                result.append(item)
    return result
