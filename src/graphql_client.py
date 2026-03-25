from __future__ import annotations

import logging
import sys

import requests

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"

REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        nameWithOwner
        description
        primaryLanguage { name }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { node { name } size }
        }
        isPrivate
        isFork
        isArchived
        createdAt
        updatedAt
        pushedAt
        defaultBranchRef { name }
        stargazerCount
        forkCount
        issues(states: OPEN) { totalCount }
        diskUsage
        url
        repositoryTopics(first: 10) { nodes { topic { name } } }
        releases(last: 5) { totalCount nodes { tagName publishedAt } }
      }
    }
  }
}
"""


def bulk_fetch_repos(username: str, token: str) -> list[dict]:
    """Fetch all repos via GraphQL, returning dicts compatible with REST API format.

    Replaces list_repos + get_languages in a single paginated query.
    """
    session = requests.Session()
    session.headers.update({
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
    })

    all_repos: list[dict] = []
    cursor: str | None = None
    page = 0

    while True:
        page += 1
        variables = {"login": username, "cursor": cursor}
        response = session.post(
            GRAPHQL_URL,
            json={"query": REPOS_QUERY, "variables": variables},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            logger.warning("GraphQL errors: %s", data["errors"])
            break

        repos_data = data["data"]["user"]["repositories"]
        nodes = repos_data["nodes"]
        print(f"  GraphQL page {page}: {len(nodes)} repos", file=sys.stderr)

        for node in nodes:
            all_repos.append(_map_to_rest_format(node))

        page_info = repos_data["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]

    return all_repos


def _map_to_rest_format(node: dict) -> dict:
    """Map a GraphQL repository node to REST API format for compatibility."""
    # Build languages dict
    languages: dict[str, int] = {}
    for edge in node.get("languages", {}).get("edges", []):
        languages[edge["node"]["name"]] = edge["size"]

    # Build topics list
    topics = [
        t["topic"]["name"]
        for t in node.get("repositoryTopics", {}).get("nodes", [])
    ]

    return {
        "name": node["name"],
        "full_name": node["nameWithOwner"],
        "description": node.get("description"),
        "language": node["primaryLanguage"]["name"] if node.get("primaryLanguage") else None,
        "private": node["isPrivate"],
        "fork": node["isFork"],
        "archived": node["isArchived"],
        "created_at": node["createdAt"],
        "updated_at": node["updatedAt"],
        "pushed_at": node.get("pushedAt"),
        "default_branch": node["defaultBranchRef"]["name"] if node.get("defaultBranchRef") else "main",
        "stargazers_count": node["stargazerCount"],
        "forks_count": node["forkCount"],
        "open_issues_count": node.get("issues", {}).get("totalCount", 0),
        "size": node.get("diskUsage", 0),
        "html_url": node["url"],
        "clone_url": node["url"] + ".git",
        "topics": topics,
        # Extra data from GraphQL not available in basic REST list
        "_languages": languages,
        "_releases": node.get("releases", {}),
        "owner": {"login": node["nameWithOwner"].split("/")[0]},
    }
