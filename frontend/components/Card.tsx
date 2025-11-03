"use client";

import { useRouter } from "next/navigation";

interface CardProps {
  repoName: string;
  eventType: string;
  summaries: string[];
  pushedAt: string;
}

export default function Card({
  repoName,
  eventType,
  summaries,
  pushedAt,
}: CardProps) {
  const router = useRouter();

  const handleCardClick = () => {
    router.push(`/details?repoName=${encodeURIComponent(repoName)}&eventType=${encodeURIComponent(eventType)}`);
  };

  return (
    <div onClick={handleCardClick} className="hover:shadow-xl hover:shadow-indigo-500/30 p-4 px-8 bg-gray-800 text-white rounded-2xl">
      <a
        href={`https://github.com/${repoName}`}
        className="font-bold text-2xl text-blue-600 hover:underline"
      >
        {repoName}
      </a>
      <h2>Event Type: {eventType}</h2>
      <ul className="list-disc list-inside">
        {summaries.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>

      <p className="text-sm text-gray-500 mt-2">Pushed at: {pushedAt}</p>
    </div>
  );
}
