import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { BindingsBrowser } from "./pages/BindingsBrowser";

export default function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <div>
          <header
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "0.75rem 1.5rem",
              borderBottom: "1px solid #ddd",
            }}
          >
            <strong>Y62DB</strong>
            <div>
              <span style={{ marginRight: "1rem", color: "#555" }}>
                Signed in as {user?.signInDetails?.loginId ?? user?.username}
              </span>
              <button onClick={signOut}>Sign out</button>
            </div>
          </header>
          <BindingsBrowser />
        </div>
      )}
    </Authenticator>
  );
}
