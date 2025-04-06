# Research AI

A powerful AI-powered research platform that helps users explore topics, analyze documents, and generate comprehensive reports with advanced language models.

## Overview

Research AI is a full-stack application that combines FastAPI, React, and Firebase to create an intuitive research workflow. The platform allows users to ask questions, receive AI-powered analysis, and explore connections between concepts through a user-friendly interface.

## Features

- **AI-Powered Research**: Ask questions and receive comprehensive analysis
- **Interactive UI**: User-friendly interface for research workflows
- **Authentication**: Secure user accounts and saved research
- **Real-time Feedback**: Provide feedback to improve the platform

## Architecture

### Backend

- **FastAPI** for the API endpoints
- **LangChain and LangGraph** for orchestrating AI workflows
- **Multiple LLM Support**: Integration with Groq, OpenAI, and Gemini models
- **Graph and Agent based Research**: Advanced research graphs, agents and chains using LangGraph and LangChain
#### Research Graph Architecture
![](backend\Images\Graph.png)

### Frontend

- **React** for the user interface
- **Tailwind CSS** for styling
- **Firebase** for authentication and data storage
- **Markdown Rendering** for displaying research outputs

#### Website Pages
Landing Page
![Landing Page](frontend\Images\Landing_Page.jpeg)

Signup Page
![Signup Page](frontend\Images\Signup_Page.jpeg)

Login Page
![Login Page](frontend\Images\Login_Page.jpeg)

New Chat Page
![New Chat Page](frontend\Images\New_Chat_Page.jpeg)

Previous Chat Page
![Previous Chat Page](frontend\Images\Previous_Chat_Page.jpeg)

Feedback Page
![Feedback Page](frontend\Images\Feedback_Page.jpeg)

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 16+
- Firebase account

### Backend Setup

1. Clone the repository
2. Create a virtual environment
    ```bash
    python -m venv backend
    backend\Scripts\activate
    ```
3. Navigate to the backend directory
    ```bash
    cd backend
    ```
4. Install dependencies
    ```bash
    pip install -r requirements.txt
    ```
5. Create a `.env` file based on `.env.example` with your API keys
6. Run the application
    ```bash
    python main.py
    ```

### Frontend Setup

1. Navigate to the frontend directory
    ```bash
    cd frontend
    ```
2. Install dependencies
    ```bash
    npm install
    ```
3. Create a `.env` file based on `.env.example` with your Firebase credentials
4. Start the development server
    ```bash
    npm run dev
    ```

## Usage

1. **Sign Up/Login**: Create an account or log in to start researching
2. **Research with Topic and Output Format**: Enter your research topic and output format to generate a research document
3. **Ask a Question**: Type your research question in the input field
4. **Review Results**: Explore the AI-generated research with citations
5. **Provide Feedback**: Help improve the platform with your insights