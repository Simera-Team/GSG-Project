import type { ReactNode } from "react";
import BrandLogo from "./BrandLogo";
import "./PageNotice.css";

export default function PageNotice({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return <div className="page-notice"><header><BrandLogo /></header><main id="page-notice-main"><span className="page-notice-label">{label}</span><h1>{title}</h1>{children}</main></div>;
}
