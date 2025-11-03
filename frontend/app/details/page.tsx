"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import JSONPretty from "react-json-pretty";
import "react-json-pretty/themes/monikai.css";
import HeatMap from "@uiw/react-heat-map";
import { Tooltip } from 'react-tooltip';

interface DetailsData {
  summary: {
    id: number;
    payload: any;
    summary: string;
    created_at: string;
  } | null;
  accidents: Array<{
    id: number;
    accident_type: string;
    timestamp: string;
    repo_name: string;
  }>;
}

export default function DetailsPage() {
  const [data, setData] = useState<DetailsData>();
  const [summaries, setSummaries] = useState<String[]>();
  const [heatmapValue, setHeatmapValue] = useState<any[]>([]);
  const searchParams = useSearchParams();
  const repoName = searchParams.get("repoName");

  useEffect(() => {
    if (!repoName) return;

    fetch(
      `http://localhost:8000/details?repo_name=${encodeURIComponent(repoName)}`
    )
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch details");
        return res.json();
      })
      .then((data) => {
        setData(data);
        setSummaries(JSON.parse(data.summary.summary));
        console.log(data);

        const value = data?.accidents.reduce((acc: any[], accident: any) => {
          const date = new Date(accident.timestamp).toISOString().split('T')[0];
          const existing = acc.find(item => item.date === date);
          if (existing) {
            existing.count += 1;
          } else {
            acc.push({ date, count: 1 });
          }
          return acc;
        }, []) || [];
        console.log(value)
        setHeatmapValue(value);
      });
  }, [repoName]);

  return (
    <div className="container mx-auto px-4 mt-8">
      <h1 className="text-2xl font-bold">
        {data?.summary?.payload?.repo?.name ?? "No data available"}
      </h1>
      <ul className="list-disc list-inside mb-4">
        {summaries?.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
      <JSONPretty
        id="json-pretty"
        data={data?.summary?.payload}
        theme="monikai"
      ></JSONPretty>

      <div className="bg-white p-4 relative mt-4">
        <h1 className="text-black text-2xl">Heatmap of force pushes</h1>
        <HeatMap
          value={heatmapValue}
          width={730}
          weekLabels={["", "Mon", "", "Wed", "", "Fri", ""]}
          startDate={new Date(new Date().setFullYear(new Date().getFullYear() - 1))}
          rectRender={(props, data) => {
            return ( 
              <rect 
                {...props} 
                data-tooltip-id="heatmap-tooltip"
                data-tooltip-content={`count: ${data.count || 0}`}
              />
            );
          }}
        />
        <Tooltip id="heatmap-tooltip" />
      </div>
    </div>
  );
}
