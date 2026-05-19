import React from "react";
import { TravelFrogMascot } from "./TravelFrogMascots";

interface Props {
  variant?: "backpack" | "passport" | "accountant" | "cashier";
  title: string;
  subtitle?: string;
  size?: number;
}

/** Empty state with TravelFrogMascot and title/subtitle. */
export function FrogEmptyState({ variant = "backpack", title, subtitle, size = 100 }: Props) {
  return (
    <div className="frog-empty">
      <TravelFrogMascot variant={variant} size={size} />
      <div className="frog-empty-title">{title}</div>
      {subtitle && <div className="frog-empty-subtitle">{subtitle}</div>}
    </div>
  );
}
