export async function POST(request: Request) {
  const projectId = 'prj_ezWS2uvZznYm7KV0BYkBLqCqeBiO';
  const teamID = 'team_Hl6JgWgLTOkZvaEf97ZIq9dx';
  const route = `${projectId}/pause?teamID=${teamID}`;

  await fetch(`https://api.vercel.com/v1/projects/${route}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.VERCEL_TOKEN}`,
    },
  });

  return new Response('Project paused', { status: 200 });
}