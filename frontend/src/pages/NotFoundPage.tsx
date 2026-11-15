import { Link } from "react-router-dom";
import PageNotice from "../components/common/PageNotice";

export default function NotFoundPage() {
  return <PageNotice label="404 - Page not found" title="We couldn't find that page.">
    <p>The link may be out of date, or the address may be incorrect. Return to CVerge to continue.</p>
    <div className="page-notice-actions"><Link to="/">Go to Home</Link></div>
  </PageNotice>;
}
