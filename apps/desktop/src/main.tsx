import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Overlay from "./components/Overlay";
import "./styles.css";

// Two windows share one bundle: the overlay window loads /#/overlay,
// the main window loads the app shell.
const isOverlay = window.location.hash === "#/overlay";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isOverlay ? <Overlay /> : <App />}</React.StrictMode>,
);
