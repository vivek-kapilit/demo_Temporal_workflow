import { Link, useParams } from "react-router-dom";
import PaymentDetails from "../components/PaymentDetails";

export default function PaymentPage() {
  const { workflowId } = useParams();
  return (
    <div>
      <p><Link to="/">← Back to dashboard</Link></p>
      <PaymentDetails workflowId={workflowId} />
    </div>
  );
}
