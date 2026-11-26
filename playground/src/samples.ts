import type { Choices } from "./leak";

export interface Sample {
  id: "careless" | "careful";
  label: string;
  about: string;
  choices: Choices;
  /** The checks this sample is expected to trip, in report order. */
  expect: string[];
}

export const SAMPLES: Sample[] = [
  {
    id: "careless",
    label: "A careless split",
    about:
      "Made-up subscription data, 2,000 rows. The rows were shuffled and cut 80/20, the way most tutorials do it.",
    choices: { target: "churned", entities: ["customer_id"], time: "month", ignore: [] },
    expect: ["single_feature", "entity_overlap", "time"],
  },
  {
    id: "careful",
    label: "A careful split",
    about:
      "The same rows, split by customer so nobody is on both sides, without the column that is only filled in after a customer leaves. It is not a split in time, so no date column is set.",
    choices: { target: "churned", entities: ["customer_id"], time: "", ignore: [] },
    expect: [],
  },
];
