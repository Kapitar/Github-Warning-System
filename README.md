# GitHub Incident Monitor

A real-time monitoring system that detects and summarizes GitHub incidents including force pushes and spam activity across public repositories. Uses AI to generate summaries of detected incidents and find patterns.

## Features

- **Real-time Event Streaming**: SSE-based live updates of GitHub incidents
- **Force Push Detection**: Automatically detects force pushes to main/master branches
- **AI-Powered Summaries**: Uses OpenAI to generate contextual incident summaries
- **Activity Analytics**: Visualize incident patterns with charts and heatmaps
- **Spam Detection**: Identifies suspicious issue/PR creation patterns
- **Historical Pattern Tracking**: Stores and analyzes incident history

## Architecture

### Backend (FastAPI + Python)
- **FastAPI**: REST API and SSE streaming endpoints
- **Redis**: Event queue for asynchronous processing
- **SQLModel**: Database ORM for SQLite/PostgreSQL
- **OpenAI API**: AI-powered incident summarization
- **GitHub API**: Real-time event polling with rate limiting

### Frontend (Next.js + React)
- **Next.js 14**: React framework
- **TailwindCSS**: Utility-first styling
- **Recharts**: Bar charts for temporal analysis
- **React Heat Map**: GitHub-style contribution heatmaps
- **Server-Sent Events**: Real-time incident updates
