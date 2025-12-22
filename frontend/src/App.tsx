/**
 * NSE Trader - Main Application Entry Point
 * 
 * Institutional-grade Nigerian Stock Exchange trading platform.
 * Redesigned for clarity, professionalism, and decision-making.
 */

import { useState } from 'react';
import './styles/design-system.css';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import Signals from './pages/Signals';
import Screener from './pages/Screener';
import Watchlist from './pages/Watchlist';
import Learn from './pages/Learn';

type Page = 'dashboard' | 'screener' | 'recommendations' | 'watchlist' | 'learn';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');

  const renderPage = () => {
    switch (currentPage) {
      case 'screener':
        return <Screener />;
      case 'recommendations':
        return <Signals />;
      case 'watchlist':
        return <Watchlist />;
      case 'learn':
        return <Learn />;
      case 'dashboard':
      default:
        return <Dashboard />;
    }
  };

  return (
    <MainLayout onNavigate={(page) => setCurrentPage(page as Page)} currentPage={currentPage}>
      {renderPage()}
    </MainLayout>
  );
}

export default App;
