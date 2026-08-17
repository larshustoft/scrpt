import { redirect } from "next/navigation";

// The front room was renamed — old links land in the Study.
export default function HQRedirect() {
  redirect("/study");
}
