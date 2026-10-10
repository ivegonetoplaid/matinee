// The Back panel's answers: every answer of the walk in the order given, each under the question it answered, and
// where a tap on it goes. A tap asks that question again, with that answer and every later one forgotten.

// `walk` holds sourceAsk/sourceSay (the source question and its answer; null when not asked or not answered),
// doorAsk/firstSay (the doors' question and the door), and asks/says (each later question and its answer). Each row
// is { ask, say, to }: `to` is "source" (ask the source question again), "doors" (the doors again), or the number of
// later answers to keep (ask the question after them again).
export function answerRows(walk) {
  const rows = [];
  if (walk.sourceSay !== null) rows.push({ ask: walk.sourceAsk, say: walk.sourceSay, to: "source" });
  if (walk.firstSay !== null) rows.push({ ask: walk.doorAsk, say: walk.firstSay, to: "doors" });
  walk.says.forEach((say, k) => rows.push({ ask: walk.asks[k], say, to: k }));
  return rows;
}

// The walk's answers with only the first `kept` left: what asking again the question after them needs. The three
// lists stay one answer each; a walk where they have drifted apart is refused rather than sent to a wrong question.
export function forget(walk, kept) {
  const { answers, says, asks } = walk;
  if (answers.length !== says.length || says.length !== asks.length) {
    throw new Error(`the walk's answers (${answers.length}), words (${says.length}) and questions (${asks.length}) differ`);
  }
  return { answers: answers.slice(0, kept), says: says.slice(0, kept), asks: asks.slice(0, kept), rushed: false };
}

// Takes `row`'s way back: `ways` holds source(), doors() and reask(kept).
export function wayTo(row, ways) {
  if (row.to === "source") return ways.source();
  if (row.to === "doors") return ways.doors();
  return ways.reask(row.to);
}
