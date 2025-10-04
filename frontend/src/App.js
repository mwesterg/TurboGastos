import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Container, Row, Col, Card, Table, Alert, Form } from 'react-bootstrap';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';
const API_KEY = process.env.REACT_APP_API_KEY;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'x-api-key': API_KEY }
});

function App() {
  const [allMessages, setAllMessages] = useState([]);
  const [error, setError] = useState('');
  const [senders, setSenders] = useState([]);
  const [selectedUser, setSelectedUser] = useState('All Users');

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const uniqueSenders = ['All Users', ...new Set(allMessages.map(msg => msg.sender_name))];
    setSenders(uniqueSenders);
  }, [allMessages]);

  const fetchData = async () => {
    try {
      setError('');
      const messagesRes = await apiClient.get('/messages?limit=1000'); // Fetch more messages for better filtering
      setAllMessages(messagesRes.data);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch data. Make sure the worker API is running and the API key is correct.');
    }
  };

  const filteredMessages = useMemo(() => {
    if (selectedUser === 'All Users') {
      return allMessages;
    }
    return allMessages.filter(msg => msg.sender_name === selectedUser);
  }, [allMessages, selectedUser]);

  const summary = useMemo(() => {
    if (!filteredMessages.length) {
      return { message_count: 0, total_amount: 0, last_message_ts: null };
    }

    const totalAmount = filteredMessages.reduce((acc, msg) => acc + (msg.amount || 0), 0);
    const lastMessage = filteredMessages.reduce((latest, msg) => (latest.ts > msg.ts ? latest : msg));

    return {
      message_count: filteredMessages.length,
      total_amount: totalAmount,
      last_message_ts: lastMessage.ts
    };
  }, [filteredMessages]);

  const formatTimestamp = (ts) => {
    if (!ts) return 'N/A';
    return new Date(ts * 1000).toLocaleString();
  };

  const getCategoryData = () => {
    const categoryMap = filteredMessages.reduce((acc, msg) => {
      if (msg.category && msg.amount) {
        acc[msg.category] = (acc[msg.category] || 0) + msg.amount;
      }
      return acc;
    }, {});

    return Object.keys(categoryMap).map(key => ({ name: key, Total: categoryMap[key] }));
  };

  return (
    <Container fluid className="App">
      <Row className="mb-4 align-items-center">
        <Col md={8}>
          <h1>TurboGastos Dashboard</h1>
        </Col>
        <Col md={4}>
          <Form.Group controlId="userFilter">
            <Form.Label>Filter by User</Form.Label>
            <Form.Select value={selectedUser} onChange={e => setSelectedUser(e.target.value)}>
              {senders.map(sender => (
                <option key={sender} value={sender}>{sender}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
      </Row>

      {error && <Alert variant="danger">{error}</Alert>}

      <Row className="mb-4">
        <Col md={4}>
          <Card>
            <Card.Header>Total Messages</Card.Header>
            <Card.Body>
              <Card.Title>{summary ? summary.message_count : 'Loading...'}</Card.Title>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card>
            <Card.Header>Total Amount Spent</Card.Header>
            <Card.Body>
              <Card.Title>{summary ? `${summary.total_amount.toFixed(2)}` : 'Loading...'}</Card.Title>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card>
            <Card.Header>Last Message Received</Card.Header>
            <Card.Body>
              <Card.Title>{summary ? formatTimestamp(summary.last_message_ts) : 'Loading...'}</Card.Title>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="mb-4">
        <Col>
          <Card>
            <Card.Header>Expenses by Category</Card.Header>
            <Card.Body>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={getCategoryData()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Total" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <Card>
            <Card.Header>Recent Messages</Card.Header>
            <Card.Body>
              <Table striped bordered hover responsive size="sm">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Sender</th>
                    <th>Body</th>
                    <th>Amount</th>
                    <th>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMessages.length > 0 ? filteredMessages.map(msg => (
                    <tr key={msg.wid}>
                      <td>{formatTimestamp(msg.ts)}</td>
                      <td>{msg.sender_name}</td>
                      <td>{msg.body}</td>
                      <td>{msg.amount ? `${msg.amount.toFixed(2)}` : 'N/A'}</td>
                      <td>{msg.category || 'N/A'}</td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="5" className="text-center">No messages found.</td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

    </Container>
  );
}

export default App;