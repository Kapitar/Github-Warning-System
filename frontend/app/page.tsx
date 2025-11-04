"use client";

import { useState, useEffect } from "react";
import Card from "@/components/Card";

export default function Home() {
  const [activities, setActivities] = useState<any[]>([]);

  useEffect(() => {
    const eventSource = new EventSource("http://localhost:8000/stream");
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setActivities((prevData) => {
        const newActivities = [data, ...prevData];
        return newActivities;
      });
    };
    eventSource.onerror = () => {
      console.error("Error connecting to SSE server.");
      eventSource.close();
    };
    return () => {
      eventSource.close();
    };
  }, []);

  return (
    <div className="container mx-auto px-2">
      <div className="flex justify-between">
        <h1 className="text-5xl font-bold text-white my-4">
          Github incident summaries
        </h1>
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
            <div className="absolute inset-0 w-3 h-3 bg-green-500 rounded-full animate-ping opacity-75"></div>
          </div>
          <span className="text-green-500 font-semibold">LIVE</span>
        </div>
      </div>
      <div className="flex flex-col gap-y-4">
      {activities
        .filter((activity) => {
          try {
            if (activity.summary) {
              JSON.parse(activity.summary);
              return true;
            }
            return false;
          } catch (error) {
            console.warn('Skipping invalid activity:', activity.id, error);
            return false;
          }
        })
        .map((activity, index) => (
          <Card
            key={activity.id || index}
            repoName={activity.payload.repo.name}
            eventType={activity.payload.type}
            summaries={JSON.parse(activity.summary)}
            pushedAt={activity.created_at}
          />
        ))}
      </div>
    </div>
  );
}
