import { useState } from 'react';
import { collection, addDoc } from 'firebase/firestore';
import { db } from '../firebase';
import { useAuth } from '../context/AuthContext';
import { Link } from 'react-router-dom';

export default function Feedback() {
  const [feedbackType, setFeedbackType] = useState('General Feedback');
  const [satisfaction, setSatisfaction] = useState('');
  const [comments, setComments] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { currentUser } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!currentUser) {
      setError('You must be logged in to submit feedback');
      return;
    }

    if (!satisfaction || !comments) {
      setError('Please fill all required fields');
      return;
    }

    setLoading(true);
    try {
      await addDoc(collection(db, 'feedback'), {
        userId: currentUser.uid,
        userEmail: currentUser.email,
        feedbackType,
        satisfaction,
        comments,
        createdAt: new Date()
      });
      setSubmitted(true);
      setError('');
    } catch (err) {
      console.error('Error submitting feedback:', err);
      setError('Failed to submit feedback. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (!currentUser) {
    return (
      <div className="pt-16">
        <div className="max-w-md mx-auto mt-10 p-6 bg-white rounded-lg shadow">
          <h2 className="text-2xl font-bold mb-4">Authentication Required</h2>
          <p className="mb-4">Please log in to submit feedback.</p>
          <Link 
            to="/login" 
            className="px-4 py-2 bg-blue-900 text-white rounded hover:bg-blue-700"
          >
            Go to Login
          </Link>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="pt-16">
        <div className="max-w-md mx-auto mt-10 p-6 bg-white rounded-lg shadow">
          <h2 className="text-2xl font-bold mb-4">Thank You!</h2>
          <p>Your feedback has been submitted successfully.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-16">
      <div className="max-w-md mx-auto mt-10 p-6 bg-white rounded-lg shadow mb-8">
        <h1 className="text-2xl font-bold mb-6">Share Your Feedback</h1>
        {error && <div className="text-red-500 mb-4">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="mb-6">
            <h3 className="font-medium mb-3">Feedback Type</h3>
            <select
              value={feedbackType}
              onChange={(e) => setFeedbackType(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded"
            >
              <option>General Feedback</option>
              <option>Bug Report</option>
              <option>Feature Request</option>
            </select>
          </div>
          
          <div className="mb-6">
            <h3 className="font-medium mb-3">How satisfied are you with the platform? *</h3>
            <div className="space-y-2">
              {['Very Satisfied', 'Satisfied', 'Neutral', 'Unsatisfied'].map((option) => (
                <label key={option} className="flex items-center">
                  <input
                    type="radio"
                    name="satisfaction"
                    value={option}
                    checked={satisfaction === option}
                    onChange={() => setSatisfaction(option)}
                    className="mr-2"
                    required
                  />
                  {option}
                </label>
              ))}
            </div>
          </div>
          
          <div className="mb-6">
            <h3 className="font-medium mb-3">Comments *</h3>
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Please share your thoughts, suggestions, or report issues..."
              className="w-full p-3 border border-gray-300 rounded h-32"
              required
            />
          </div>
          
          <div className="flex justify-end space-x-4">
            <button
              type="submit"
              className="px-4 py-2 bg-blue-900 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={loading}
            >
              {loading ? 'Submitting...' : 'Submit Feedback'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}