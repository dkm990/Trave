import React from "react";
import { TravelFrogMascot } from "./TravelFrogMascots";

interface Props {
  variant?: "travel" | "accountant" | "cashier" | "passport";
  size?: number;
}

/** Hero frog — delegates to TravelFrogMascot. "travel" → "backpack". */
export function FrogHero({ variant = "travel", size = 80 }: Props) {
  const map: Record<string, "backpack" | "accountant" | "cashier" | "passport"> = {
    travel: "backpack",
    accountant: "accountant",
    cashier: "cashier",
    passport: "passport",
  };

  return <TravelFrogMascot variant={map[variant]} size={size} />;
}
