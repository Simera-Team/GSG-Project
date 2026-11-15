import { NavLink } from "react-router-dom";

function Navbar() {
  return (
    <header className="navbar">
      <NavLink to="/" className="navbar-logo">
        CVerge
      </NavLink>

      <nav className="navbar-links">
        <NavLink to="/">Home</NavLink>
        <NavLink to="/upload">Upload Documents</NavLink>
        <NavLink to="/profile">My Profile</NavLink>
        <NavLink to="/dashboard">Dashboard</NavLink>
      </nav>
    </header>
  );
}

export default Navbar;