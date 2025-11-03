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
      <h1 className="text-5xl font-bold text-white my-4">
        Github incident summaries
      </h1>
      <div className="flex flex-col gap-y-4">
        {activities.map((activity, index) => (
          <Card
            key={index}
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
