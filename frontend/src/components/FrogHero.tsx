import React from "react";
import { TravelFrogMascot } from "./TravelFrogMascots";

interface Props {
  variant?: "travel" | "accountant" | "cashier" | "passport" | "pilot";
  size?: number;
}

/** Hero frog — delegates to TravelFrogMascot. "travel" → "backpack". */
export function FrogHero({ variant = "travel", size = 80 }: Props) {
  const map: Record<string, "backpack" | "accountant" | "cashier" | "passport" | "pilot"> = {
    travel: "backpack",
    accountant: "accountant",
    cashier: "cashier",
    passport: "passport",
    pilot: "pilot",
  };

  return <TravelFrogMascot variant={map[variant]} size={size} />;
}
