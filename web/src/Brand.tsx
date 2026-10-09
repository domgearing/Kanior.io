import lightLogo from "../../verelo-design-system/logos/verelo-lockup-color.png";
import darkLogo from "../../verelo-design-system/logos/verelo-lockup-color-reverse.png";

export function Brand() {
  return (
    <div className="brand" aria-label="Verelo">
      <img className="brand-light" src={lightLogo} alt="Verelo" />
      <img className="brand-dark" src={darkLogo} alt="Verelo" />
    </div>
  );
}
