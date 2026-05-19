import React from "react";
import { TravelFrogMascot } from "./TravelFrogMascots";

interface Props {
  size?: number;
}

/** Tiny frog badge — delegates to TravelFrogMascot. */
export function FrogBadge({ size = 24 }: Props) {
  return (
    <TravelFrogMascot
      variant="backpack"
      size={size}
    />
  );
}
