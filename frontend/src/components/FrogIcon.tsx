import React from "react";
import { TravelFrogMascot } from "./TravelFrogMascots";

interface Props {
  variant?: "default" | "hero" | "backpack" | "suitcase" | "passport" | "calc" | "glasses";
  size?: number;
  className?: string;
}

const variantMap: Record<string, "backpack" | "accountant" | "cashier" | "passport"> = {
  default: "backpack",
  hero: "backpack",
  backpack: "backpack",
  suitcase: "backpack",
  passport: "passport",
  calc: "cashier",
  glasses: "accountant",
};

export function FrogIcon({ variant = "default", size = 48, className }: Props) {
  return (
    <TravelFrogMascot
      variant={variantMap[variant] || "backpack"}
      size={size}
      className={className}
    />
  );
}
