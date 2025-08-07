// src/components/SimpleNotification.tsx
import React, { useState, useEffect, useCallback } from 'react';
import './SimpleNotification.css';

type NotificationType = 'success' | 'error' | 'info';

interface NotificationProps {
  message: string;
  type: NotificationType;
  onClose: () => void;
}

const SimpleNotification: React.FC<NotificationProps> = ({ message, type, onClose }) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(true);
    const timer = setTimeout(() => {
      handleClose();
    }, 3000); // 3秒后自动关闭

    return () => clearTimeout(timer);
  }, [message]);

  const handleClose = useCallback(() => {
    setVisible(false);
    // 等待动画结束后再调用onClose
    setTimeout(onClose, 300);
  }, [onClose]);

  return (
    <div className={`simple-notification ${type} ${visible ? 'visible' : ''}`}>
      <span className="notification-message">{message}</span>
      <button className="notification-close-btn" onClick={handleClose}>
        &times;
      </button>
    </div>
  );
};

export default SimpleNotification;

