import type { Metadata } from "next";
import { Familjen_Grotesk, Literata } from "next/font/google";
import { Rail } from "@/components/Rail";
import "./globals.css";

const display = Familjen_Grotesk({ subsets: ["latin"], variable: "--font-display" });
const reading = Literata({ subsets: ["latin"], variable: "--font-reading" });

export const metadata: Metadata = {
  title: "LazyGenius",
  description: "Lecture notes where every claim is checked against the slide it cites.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${reading.variable}`}>
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        <Rail />
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
