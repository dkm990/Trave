import React from "react";

type MascotVariant = "backpack" | "accountant" | "cashier" | "passport" | "pilot";

type Props = {
  variant: MascotVariant;
  size?: number;
  className?: string;
};

const mascotImages: Record<MascotVariant, string> = {
  backpack: "/assets/mascots/backpack.png",
  accountant: "/assets/mascots/accountant.png",
  cashier: "/assets/mascots/cashier.png",
  passport: "/assets/mascots/passport.png",
  pilot: "/assets/mascots/pilot.png",
};

export function TravelFrogMascot({
  variant,
  size = 160,
  className,
}: Props) {
  return (
    <img
      src={mascotImages[variant]}
      alt={`Travel Frog ${variant}`}
      width={size}
      height={size * 1.5}
      className={className}
      style={{ objectFit: "contain" }}
    />
  );
}
