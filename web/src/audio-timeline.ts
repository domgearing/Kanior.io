export type TimedWord = {
  text: string;
  start_ms: number;
  end_ms: number;
  start_character: number;
  end_character: number;
};

export function activeTimedIndex(
  items: Array<{ start_ms: number | null; end_ms: number | null }>,
  positionMs: number,
): number {
  return items.findIndex(
    (item) =>
      item.start_ms !== null &&
      item.end_ms !== null &&
      item.start_ms <= positionMs &&
      positionMs < item.end_ms,
  );
}

export function wordParts(text: string, words: TimedWord[]) {
  const characters = Array.from(text);
  const parts: Array<{ text: string; wordIndex: number | null }> = [];
  let cursor = 0;
  for (const [index, word] of words.entries()) {
    if (
      word.start_character < cursor ||
      word.end_character > characters.length ||
      characters.slice(word.start_character, word.end_character).join("") !==
        word.text
    ) {
      return [{ text, wordIndex: null }];
    }
    if (word.start_character > cursor) {
      parts.push({
        text: characters.slice(cursor, word.start_character).join(""),
        wordIndex: null,
      });
    }
    parts.push({ text: word.text, wordIndex: index });
    cursor = word.end_character;
  }
  if (cursor < characters.length) {
    parts.push({ text: characters.slice(cursor).join(""), wordIndex: null });
  }
  return parts;
}
