import './components/workspace/studio.css';
import './components/workspace/studioPolish.css';
import './components/workspace/studioWork.css';
import React from 'react';import {createRoot} from 'react-dom/client';
import App from './App';import './styles/global.css';import './styles/barqPolish.css';import './styles/barqInterface.css';
const host=document.getElementById('root');if(!host)throw new Error('Missing root element');
createRoot(host).render(<React.StrictMode><App/></React.StrictMode>);
