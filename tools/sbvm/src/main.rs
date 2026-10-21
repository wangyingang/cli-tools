use std::cmp::Ordering;
use std::collections::HashSet;
use std::env;
use std::fs;
use std::io::{BufWriter, Write};
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Path, PathBuf};
use std::process;

use anyhow::{Context, Result, anyhow, bail};
use chrono::{DateTime, Utc};
use clap::{Parser, Subcommand, ValueEnum};
use flate2::read::GzDecoder;
use reqwest::StatusCode;
use reqwest::blocking::{Client, Response};
use reqwest::header::{ACCEPT, AUTHORIZATION, HeaderMap, HeaderValue, USER_AGENT};
use semver::Version;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tar::Archive;

const OWNER: &str = "SagerNet";
const REPO: &str = "sing-box";
const API_BASE: &str = "https://api.github.com";
const API_VERSION: &str = "2026-03-10";
const DEFAULT_BIN_NAME: &str = "sing-box";
const DISPLAY_LABEL: &str = "sing-box version manager";
const DEFAULT_LS_REMOTE_LIMIT: usize = 20;
const MAX_LS_REMOTE_LIMIT: usize = 100;

#[derive(Parser, Debug)]
#[command(name = "sbvm")]
#[command(about = "sing-box version manager")]
struct Cli {
    #[arg(long, global = true, help = "Print machine-readable JSON")]
    json: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    Doctor,
    LsRemote {
        #[arg(long, default_value_t = DEFAULT_LS_REMOTE_LIMIT, help = "Maximum number of versions to display")]
        limit: usize,
        #[arg(long, help = "Show only stable releases and exclude prereleases")]
        release: bool,
    },
    Install {
        release: String,
        #[arg(long, value_enum, default_value_t = InstallTarget::Auto)]
        target: InstallTarget,
        #[arg(long)]
        force: bool,
    },
    Ls,
    Use {
        release: String,
        #[arg(long, help = "Create a symlink instead of copying the binary")]
        link: bool,
        #[arg(long, help = "Replace an existing unmanaged target binary")]
        force: bool,
    },
    Uninstall {
        release: String,
    },
    Current,
    Request {
        path: String,
    },
}

#[derive(Clone, Copy, Debug, Serialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
enum InstallTarget {
    Auto,
    DarwinArm64,
    DarwinAmd64,
    LinuxAmd64,
    LinuxArm64,
}

impl InstallTarget {
    fn resolved(self) -> Result<Self> {
        match self {
            Self::Auto => match (env::consts::OS, env::consts::ARCH) {
                ("macos", "aarch64") => Ok(Self::DarwinArm64),
                ("macos", "x86_64") => Ok(Self::DarwinAmd64),
                ("linux", "x86_64") => Ok(Self::LinuxAmd64),
                ("linux", "aarch64") => Ok(Self::LinuxArm64),
                (os, arch) => {
                    bail!("unsupported current machine {os}/{arch}; use --target explicitly")
                }
            },
            other => Ok(other),
        }
    }

    fn asset_suffixes(self) -> &'static [&'static str] {
        match self {
            Self::Auto => &[],
            Self::DarwinArm64 => &["-darwin-arm64.tar.gz"],
            Self::DarwinAmd64 => &["-darwin-amd64.tar.gz"],
            Self::LinuxAmd64 => &[
                "-linux-amd64.tar.gz",
                "-linux-amd64-glibc.tar.gz",
                "-linux-amd64-musl.tar.gz",
            ],
            Self::LinuxArm64 => &[
                "-linux-arm64.tar.gz",
                "-linux-arm64-glibc.tar.gz",
                "-linux-arm64-musl.tar.gz",
            ],
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::DarwinArm64 => "darwin-arm64",
            Self::DarwinAmd64 => "darwin-amd64",
            Self::LinuxAmd64 => "linux-amd64",
            Self::LinuxArm64 => "linux-arm64",
        }
    }
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct ReleaseAsset {
    id: u64,
    name: String,
    content_type: Option<String>,
    size: u64,
    browser_download_url: String,
    download_count: Option<u64>,
    updated_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct Release {
    id: u64,
    tag_name: String,
    name: Option<String>,
    draft: bool,
    prerelease: bool,
    html_url: String,
    published_at: Option<DateTime<Utc>>,
    assets: Vec<ReleaseAsset>,
}

#[derive(Debug, Default, Deserialize, Serialize)]
struct AppState {
    current_version: Option<String>,
    managed_binary_path: Option<PathBuf>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct InstallMetadata {
    version: String,
    asset_name: String,
    target: String,
    source_url: String,
    installed_at: DateTime<Utc>,
    binary_rel_path: PathBuf,
}

#[derive(Debug)]
struct InstallEntry {
    metadata: InstallMetadata,
    version_dir: PathBuf,
}

#[derive(Debug)]
struct AppPaths {
    root: PathBuf,
    versions_dir: PathBuf,
    downloads_dir: PathBuf,
    state_file: PathBuf,
    target_bin_dir: PathBuf,
    target_binary: PathBuf,
}

impl AppPaths {
    fn detect() -> Result<Self> {
        let home = env::var_os("HOME")
            .map(PathBuf::from)
            .context("HOME is not set; cannot determine sbvm directories")?;
        let root = home.join(".sbvm");
        let versions_dir = root.join("versions");
        let downloads_dir = root.join("downloads");
        let state_file = root.join("state.json");
        let target_bin_dir = home.join(".local/bin");
        let target_binary = target_bin_dir.join(DEFAULT_BIN_NAME);
        Ok(Self {
            root,
            versions_dir,
            downloads_dir,
            state_file,
            target_bin_dir,
            target_binary,
        })
    }

    fn ensure_base_dirs(&self) -> Result<()> {
        fs::create_dir_all(&self.root)
            .with_context(|| format!("create {}", self.root.display()))?;
        fs::create_dir_all(&self.versions_dir)
            .with_context(|| format!("create {}", self.versions_dir.display()))?;
        fs::create_dir_all(&self.downloads_dir)
            .with_context(|| format!("create {}", self.downloads_dir.display()))?;
        Ok(())
    }
}

#[derive(Debug)]
struct GitHubClient {
    http: Client,
    token: Option<String>,
}

impl GitHubClient {
    fn new() -> Result<Self> {
        let http = Client::builder()
            .build()
            .context("build HTTP client failed")?;
        Ok(Self {
            http,
            token: env::var("GITHUB_TOKEN").ok().filter(|v| !v.is_empty()),
        })
    }

    fn auth_source(&self) -> &'static str {
        if self.token.is_some() {
            "env"
        } else {
            "missing"
        }
    }

    fn api_get(&self, path: &str) -> Result<Response> {
        let url = if path.starts_with("http://") || path.starts_with("https://") {
            path.to_string()
        } else {
            format!("{API_BASE}{path}")
        };
        let mut headers = HeaderMap::new();
        headers.insert(
            ACCEPT,
            HeaderValue::from_static("application/vnd.github+json"),
        );
        headers.insert(
            "X-GitHub-Api-Version",
            HeaderValue::from_static(API_VERSION),
        );
        headers.insert(USER_AGENT, HeaderValue::from_static("sbvm/0.1.0"));
        if let Some(token) = &self.token {
            headers.insert(
                AUTHORIZATION,
                HeaderValue::from_str(&format!("Bearer {token}"))
                    .context("invalid GITHUB_TOKEN header value")?,
            );
        }
        let response = self
            .http
            .get(&url)
            .headers(headers)
            .send()
            .with_context(|| format!("GET {url} failed"))?;
        if response.status().is_success() {
            Ok(response)
        } else {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            if status == StatusCode::NOT_FOUND {
                bail!("resource not found: {path}");
            }
            bail!("GitHub API error {status}: {}", compact_body(&body));
        }
    }

    fn api_get_json<T: for<'de> Deserialize<'de>>(&self, path: &str) -> Result<T> {
        let response = self.api_get(path)?;
        response
            .json::<T>()
            .with_context(|| format!("decode JSON from {path} failed"))
    }

    fn download_to_file(&self, url: &str, destination: &Path) -> Result<()> {
        let mut response = self
            .http
            .get(url)
            .header(USER_AGENT, "sbvm/0.1.0")
            .send()
            .with_context(|| format!("download {url} failed"))?;
        if !response.status().is_success() {
            bail!("download failed with status {}", response.status());
        }
        let mut file = BufWriter::new(
            fs::File::create(destination)
                .with_context(|| format!("create {}", destination.display()))?,
        );
        response
            .copy_to(&mut file)
            .with_context(|| format!("write {}", destination.display()))?;
        file.flush()
            .with_context(|| format!("flush {}", destination.display()))?;
        Ok(())
    }
}

fn main() {
    let cli = Cli::parse();
    let exit_code = match run(&cli) {
        Ok(()) => 0,
        Err(err) => {
            if cli.json {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "error": { "message": format!("{err:#}") }
                    }))
                    .unwrap()
                );
            } else {
                eprintln!("Error: {err:#}");
            }
            1
        }
    };
    process::exit(exit_code);
}

fn run(cli: &Cli) -> Result<()> {
    let paths = AppPaths::detect()?;
    let client = GitHubClient::new()?;
    match &cli.command {
        Commands::Doctor => cmd_doctor(cli.json, &client, &paths),
        Commands::LsRemote { limit, release } => {
            cmd_ls_remote(cli.json, &client, &paths, *limit, *release)
        }
        Commands::Install {
            release,
            target,
            force,
        } => cmd_install(cli.json, &client, &paths, release, *target, *force),
        Commands::Ls => cmd_ls(cli.json, &paths),
        Commands::Use {
            release,
            link,
            force,
        } => cmd_use(cli.json, &paths, release, *link, *force),
        Commands::Uninstall { release } => cmd_uninstall(cli.json, &paths, release),
        Commands::Current => cmd_current(cli.json, &paths),
        Commands::Request { path } => cmd_request(cli.json, &client, path),
    }
}

fn cmd_doctor(json_output: bool, client: &GitHubClient, paths: &AppPaths) -> Result<()> {
    paths.ensure_base_dirs()?;
    fs::create_dir_all(&paths.target_bin_dir)
        .with_context(|| format!("create {}", paths.target_bin_dir.display()))?;
    let _repo: Value = client.api_get_json(&format!("/repos/{OWNER}/{REPO}"))?;
    let path_env = env::var("PATH").unwrap_or_default();
    let bin_dir_on_path = path_env
        .split(':')
        .any(|entry| Path::new(entry) == paths.target_bin_dir);
    let output = json!({
        "tool": "sbvm",
        "label": DISPLAY_LABEL,
        "version": env!("CARGO_PKG_VERSION"),
        "repo": format!("{OWNER}/{REPO}"),
        "runtime": {
            "os": env::consts::OS,
            "arch": env::consts::ARCH,
        },
        "auth": {
            "available": client.token.is_some(),
            "source": client.auth_source(),
        },
        "paths": {
            "root": paths.root,
            "versions_dir": paths.versions_dir,
            "downloads_dir": paths.downloads_dir,
            "target_bin_dir": paths.target_bin_dir,
            "target_binary": paths.target_binary,
        },
        "checks": {
            "github_api": true,
            "bin_dir_on_path": bin_dir_on_path,
            "target_binary_exists": paths.target_binary.exists(),
        }
    });
    if json_output {
        print_json(&output)?;
    } else {
        println!("{DISPLAY_LABEL} (sbvm {})", env!("CARGO_PKG_VERSION"));
        println!("repo: {OWNER}/{REPO}");
        println!("runtime: {}/{}", env::consts::OS, env::consts::ARCH);
        println!("auth: {}", client.auth_source());
        println!("github_api: ok");
        println!(
            "bin_dir_on_path: {}",
            if bin_dir_on_path { "yes" } else { "no" }
        );
        println!("root: {}", paths.root.display());
        println!("target_binary: {}", paths.target_binary.display());
    }
    Ok(())
}

fn cmd_ls_remote(
    json_output: bool,
    client: &GitHubClient,
    paths: &AppPaths,
    limit: usize,
    release_only: bool,
) -> Result<()> {
    validate_ls_remote_limit(limit)?;
    let installed_versions = load_installed_versions(paths)?;
    let releases = fetch_releases_for_list(client, limit, release_only)?;
    if json_output {
        let output = json!({
            "repo": format!("{OWNER}/{REPO}"),
            "limit": limit,
            "release_only": release_only,
            "count": releases.len(),
            "releases": releases.iter().map(|release| json!({
                "tag_name": release.tag_name,
                "name": release.name,
                "prerelease": release.prerelease,
                "html_url": release.html_url,
                "installed": installed_versions.contains(&release.tag_name),
            })).collect::<Vec<_>>()
        });
        print_json(&output)?;
    } else {
        if releases.is_empty() {
            println!("no remote releases");
        } else {
            print_release_page(&releases, &installed_versions);
        }
    }
    Ok(())
}

fn cmd_install(
    json_output: bool,
    client: &GitHubClient,
    paths: &AppPaths,
    release_spec: &str,
    target: InstallTarget,
    force: bool,
) -> Result<()> {
    paths.ensure_base_dirs()?;
    let release = resolve_release(client, release_spec)?;
    let resolved_target = target.resolved()?;
    let asset = select_asset(&release, resolved_target)?;
    let version_dir = paths.versions_dir.join(&release.tag_name);
    if version_dir.exists() {
        if force {
            fs::remove_dir_all(&version_dir)
                .with_context(|| format!("remove {}", version_dir.display()))?;
        } else {
            bail!(
                "version {} is already installed; use --force to reinstall",
                release.tag_name
            );
        }
    }
    let archive_path = paths.downloads_dir.join(&asset.name);
    client.download_to_file(&asset.browser_download_url, &archive_path)?;
    fs::create_dir_all(&version_dir)
        .with_context(|| format!("create {}", version_dir.display()))?;
    extract_tarball(&archive_path, &version_dir)?;
    let binary_abs = find_binary_in_dir(&version_dir)?;
    let binary_rel = binary_abs
        .strip_prefix(&version_dir)
        .context("installed binary path escapes version directory")?
        .to_path_buf();
    let metadata = InstallMetadata {
        version: release.tag_name.clone(),
        asset_name: asset.name.clone(),
        target: resolved_target.label().to_string(),
        source_url: asset.browser_download_url.clone(),
        installed_at: Utc::now(),
        binary_rel_path: binary_rel,
    };
    write_metadata(&version_dir, &metadata)?;
    let output = json!({
        "installed": true,
        "version": release.tag_name,
        "target": resolved_target.label(),
        "asset_name": asset.name,
        "version_dir": version_dir,
        "archive_path": archive_path,
        "binary_path": binary_abs,
    });
    if json_output {
        print_json(&output)?;
    } else {
        println!(
            "installed {}",
            output["version"].as_str().unwrap_or_default()
        );
        println!(
            "asset: {}",
            output["asset_name"].as_str().unwrap_or_default()
        );
        println!(
            "binary: {}",
            output["binary_path"].as_str().unwrap_or_default()
        );
    }
    Ok(())
}

fn cmd_ls(json_output: bool, paths: &AppPaths) -> Result<()> {
    let state = load_state(paths)?;
    let installs = load_installs(paths)?;
    if json_output {
        let output = json!({
            "current_version": state.current_version,
            "installed": installs.iter().map(|entry| json!({
                "version": entry.metadata.version,
                "current": state.current_version.as_ref() == Some(&entry.metadata.version),
            })).collect::<Vec<_>>()
        });
        print_json(&output)?;
    } else if installs.is_empty() {
        println!("no installed versions");
    } else {
        for entry in installs {
            let marker = if state.current_version.as_ref() == Some(&entry.metadata.version) {
                "*"
            } else {
                " "
            };
            println!("{marker} {}", entry.metadata.version);
        }
    }
    Ok(())
}

fn cmd_use(
    json_output: bool,
    paths: &AppPaths,
    release: &str,
    use_link: bool,
    force: bool,
) -> Result<()> {
    let mut state = load_state(paths)?;
    let install = load_install(paths, release)?;
    let source_binary = install.version_dir.join(&install.metadata.binary_rel_path);
    if !source_binary.exists() {
        bail!(
            "installed binary missing for {}; reinstall this version",
            install.metadata.version
        );
    }
    fs::create_dir_all(&paths.target_bin_dir)
        .with_context(|| format!("create {}", paths.target_bin_dir.display()))?;
    if paths.target_binary.exists() || symlink_metadata_exists(&paths.target_binary) {
        let managed = state.managed_binary_path.as_ref() == Some(&paths.target_binary);
        if !managed && !force {
            bail!(
                "{} already exists and is not marked as sbvm-managed; use --force to replace it",
                paths.target_binary.display()
            );
        }
        remove_existing_path(&paths.target_binary)?;
    }
    if use_link {
        symlink(&source_binary, &paths.target_binary).with_context(|| {
            format!(
                "create symlink {} -> {}",
                paths.target_binary.display(),
                source_binary.display()
            )
        })?;
    } else {
        fs::copy(&source_binary, &paths.target_binary).with_context(|| {
            format!(
                "copy {} -> {}",
                source_binary.display(),
                paths.target_binary.display()
            )
        })?;
        let mut perms = fs::metadata(&paths.target_binary)
            .with_context(|| format!("read {}", paths.target_binary.display()))?
            .permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&paths.target_binary, perms)
            .with_context(|| format!("chmod {}", paths.target_binary.display()))?;
    }
    state.current_version = Some(install.metadata.version.clone());
    state.managed_binary_path = Some(paths.target_binary.clone());
    save_state(paths, &state)?;
    let output = json!({
        "active": true,
        "version": install.metadata.version,
        "mode": if use_link { "link" } else { "copy" },
        "target_binary": paths.target_binary,
        "source_binary": source_binary,
    });
    if json_output {
        print_json(&output)?;
    } else {
        println!(
            "using {} via {}",
            output["version"].as_str().unwrap_or_default(),
            output["mode"].as_str().unwrap_or_default()
        );
        println!(
            "target: {}",
            output["target_binary"].as_str().unwrap_or_default()
        );
    }
    Ok(())
}

fn cmd_uninstall(json_output: bool, paths: &AppPaths, release: &str) -> Result<()> {
    let state = load_state(paths)?;
    let install = load_install(paths, release)?;
    if state.current_version.as_ref() == Some(&install.metadata.version) {
        bail!(
            "{} is currently active; switch versions before uninstalling",
            install.metadata.version
        );
    }
    fs::remove_dir_all(&install.version_dir)
        .with_context(|| format!("remove {}", install.version_dir.display()))?;
    let archive_path = paths.downloads_dir.join(&install.metadata.asset_name);
    if archive_path.exists() {
        fs::remove_file(&archive_path)
            .with_context(|| format!("remove {}", archive_path.display()))?;
    }
    let output = json!({
        "uninstalled": true,
        "version": install.metadata.version,
        "version_dir": install.version_dir,
        "archive_path": archive_path,
    });
    if json_output {
        print_json(&output)?;
    } else {
        println!(
            "uninstalled {}",
            output["version"].as_str().unwrap_or_default()
        );
    }
    Ok(())
}

fn cmd_current(json_output: bool, paths: &AppPaths) -> Result<()> {
    let state = load_state(paths)?;
    let output = json!({
        "current_version": state.current_version,
        "target_binary": paths.target_binary,
        "exists": paths.target_binary.exists(),
    });
    if json_output {
        print_json(&output)?;
    } else if let Some(version) = output["current_version"].as_str() {
        println!("{version}");
    } else {
        println!("no active version");
    }
    Ok(())
}

fn cmd_request(json_output: bool, client: &GitHubClient, path: &str) -> Result<()> {
    let api_path = normalize_request_path(path);
    let value: Value = client.api_get_json(&api_path)?;
    if json_output {
        print_json(&value)?;
    } else {
        print_json(&value)?;
    }
    Ok(())
}

fn fetch_releases_for_list(
    client: &GitHubClient,
    limit: usize,
    release_only: bool,
) -> Result<Vec<Release>> {
    if !release_only {
        return fetch_release_page(client, 1, limit);
    }
    let mut page = 1;
    let mut releases = Vec::new();
    while releases.len() < limit {
        let chunk = fetch_release_page(client, page, MAX_LS_REMOTE_LIMIT)?;
        if chunk.is_empty() {
            break;
        }
        releases.extend(chunk.into_iter().filter(|release| !release.prerelease));
        page += 1;
    }
    releases.truncate(limit);
    Ok(releases)
}

fn fetch_release_page(client: &GitHubClient, page: usize, per_page: usize) -> Result<Vec<Release>> {
    client.api_get_json(&format!(
        "/repos/{OWNER}/{REPO}/releases?per_page={per_page}&page={page}"
    ))
}

fn resolve_release(client: &GitHubClient, release_spec: &str) -> Result<Release> {
    if release_spec == "latest" {
        return client.api_get_json(&format!("/repos/{OWNER}/{REPO}/releases/latest"));
    }
    let mut candidates = vec![release_spec.to_string()];
    if !release_spec.starts_with('v') {
        candidates.push(format!("v{release_spec}"));
    }
    let mut last_error = None;
    for candidate in candidates {
        match client
            .api_get_json::<Release>(&format!("/repos/{OWNER}/{REPO}/releases/tags/{candidate}"))
        {
            Ok(release) => return Ok(release),
            Err(err) => last_error = Some(err),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("release not found")))
}

fn select_asset<'a>(release: &'a Release, target: InstallTarget) -> Result<&'a ReleaseAsset> {
    for suffix in target.asset_suffixes() {
        if let Some(asset) = release
            .assets
            .iter()
            .find(|asset| asset.name.ends_with(suffix) && !asset.name.contains("legacy"))
        {
            return Ok(asset);
        }
    }
    bail!(
        "no precompiled asset for {} in release {}",
        target.label(),
        release.tag_name
    )
}

fn extract_tarball(archive_path: &Path, destination: &Path) -> Result<()> {
    let archive_file =
        fs::File::open(archive_path).with_context(|| format!("open {}", archive_path.display()))?;
    let tar = GzDecoder::new(archive_file);
    let mut archive = Archive::new(tar);
    archive.unpack(destination).with_context(|| {
        format!(
            "extract {} into {}",
            archive_path.display(),
            destination.display()
        )
    })
}

fn find_binary_in_dir(root: &Path) -> Result<PathBuf> {
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir).with_context(|| format!("read {}", dir.display()))? {
            let entry = entry.with_context(|| format!("scan {}", dir.display()))?;
            let path = entry.path();
            let file_type = entry
                .file_type()
                .with_context(|| format!("stat {}", path.display()))?;
            if file_type.is_dir() {
                stack.push(path);
            } else if path.file_name().and_then(|name| name.to_str()) == Some(DEFAULT_BIN_NAME) {
                return Ok(path);
            }
        }
    }
    bail!("no {} binary found after extraction", DEFAULT_BIN_NAME)
}

fn load_state(paths: &AppPaths) -> Result<AppState> {
    if !paths.state_file.exists() {
        return Ok(AppState::default());
    }
    let raw = fs::read_to_string(&paths.state_file)
        .with_context(|| format!("read {}", paths.state_file.display()))?;
    let state = serde_json::from_str(&raw)
        .with_context(|| format!("parse {}", paths.state_file.display()))?;
    Ok(state)
}

fn save_state(paths: &AppPaths, state: &AppState) -> Result<()> {
    paths.ensure_base_dirs()?;
    let body = serde_json::to_string_pretty(state).context("serialize state failed")?;
    fs::write(&paths.state_file, body)
        .with_context(|| format!("write {}", paths.state_file.display()))
}

fn write_metadata(version_dir: &Path, metadata: &InstallMetadata) -> Result<()> {
    let body = serde_json::to_string_pretty(metadata).context("serialize metadata failed")?;
    fs::write(version_dir.join("metadata.json"), body)
        .with_context(|| format!("write {}", version_dir.join("metadata.json").display()))
}

fn load_installs(paths: &AppPaths) -> Result<Vec<InstallEntry>> {
    if !paths.versions_dir.exists() {
        return Ok(Vec::new());
    }
    let mut installs = Vec::new();
    for entry in fs::read_dir(&paths.versions_dir)
        .with_context(|| format!("read {}", paths.versions_dir.display()))?
    {
        let entry = entry.with_context(|| format!("scan {}", paths.versions_dir.display()))?;
        if !entry
            .file_type()
            .with_context(|| format!("stat {}", entry.path().display()))?
            .is_dir()
        {
            continue;
        }
        let version_dir = entry.path();
        let metadata_path = version_dir.join("metadata.json");
        if !metadata_path.exists() {
            continue;
        }
        let raw = fs::read_to_string(&metadata_path)
            .with_context(|| format!("read {}", metadata_path.display()))?;
        let metadata: InstallMetadata = serde_json::from_str(&raw)
            .with_context(|| format!("parse {}", metadata_path.display()))?;
        installs.push(InstallEntry {
            metadata,
            version_dir,
        });
    }
    installs.sort_by(|a, b| compare_versions_desc(&a.metadata.version, &b.metadata.version));
    Ok(installs)
}

fn load_install(paths: &AppPaths, release: &str) -> Result<InstallEntry> {
    let installs = load_installs(paths)?;
    installs
        .into_iter()
        .find(|entry| {
            entry.metadata.version == release || entry.metadata.version == format!("v{release}")
        })
        .ok_or_else(|| anyhow!("version {release} is not installed"))
}

fn load_installed_versions(paths: &AppPaths) -> Result<HashSet<String>> {
    Ok(load_installs(paths)?
        .into_iter()
        .map(|entry| entry.metadata.version)
        .collect())
}

fn validate_ls_remote_limit(limit: usize) -> Result<()> {
    if limit == 0 || limit > MAX_LS_REMOTE_LIMIT {
        bail!("limit must be between 1 and {}", MAX_LS_REMOTE_LIMIT);
    }
    Ok(())
}

fn print_release_page(releases: &[Release], installed_versions: &HashSet<String>) {
    let version_width = releases
        .iter()
        .map(|release| release.tag_name.len())
        .max()
        .unwrap_or(0);
    for release in releases {
        println!(
            "{}",
            render_release_line(release, installed_versions, version_width)
        );
    }
}

fn render_release_line(
    release: &Release,
    installed_versions: &HashSet<String>,
    version_width: usize,
) -> String {
    let marker = if installed_versions.contains(&release.tag_name) {
        "*"
    } else {
        " "
    };
    let kind = if release.prerelease {
        "prerelease"
    } else {
        "release"
    };
    format!(
        "{marker} {:<width$}  {kind}",
        release.tag_name,
        width = version_width
    )
}

fn compare_versions_desc(left: &str, right: &str) -> Ordering {
    match (parse_version(left), parse_version(right)) {
        (Some(lhs), Some(rhs)) => rhs.cmp(&lhs),
        _ => right.cmp(left),
    }
}

fn parse_version(raw: &str) -> Option<Version> {
    let mut normalized = raw.trim_start_matches('v').to_string();
    let (core, suffix) = match normalized.split_once('-') {
        Some((core, suffix)) => (core.to_string(), Some(suffix.to_string())),
        None => (normalized.clone(), None),
    };
    if core.matches('.').count() == 1 {
        normalized = format!("{core}.0");
        if let Some(suffix) = suffix {
            normalized.push('-');
            normalized.push_str(&suffix);
        }
    }
    Version::parse(&normalized).ok()
}

fn print_json(value: &Value) -> Result<()> {
    println!(
        "{}",
        serde_json::to_string_pretty(value).context("serialize JSON output failed")?
    );
    Ok(())
}

fn normalize_request_path(path: &str) -> String {
    if path.starts_with("http://") || path.starts_with("https://") {
        path.to_string()
    } else if path.starts_with('/') {
        path.to_string()
    } else {
        format!("/{path}")
    }
}

fn compact_body(body: &str) -> String {
    body.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn remove_existing_path(path: &Path) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_dir() {
                fs::remove_dir_all(path).with_context(|| format!("remove {}", path.display()))
            } else {
                fs::remove_file(path).with_context(|| format!("remove {}", path.display()))
            }
        }
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(err) => Err(err).with_context(|| format!("stat {}", path.display())),
    }
}

fn symlink_metadata_exists(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_sort_prefers_newer_semver() {
        let mut versions = vec![
            "v1.13.9".to_string(),
            "v1.14.0-alpha.15".to_string(),
            "v1.12.8".to_string(),
        ];
        versions.sort_by(|a, b| compare_versions_desc(a, b));
        assert_eq!(
            versions,
            vec![
                "v1.14.0-alpha.15".to_string(),
                "v1.13.9".to_string(),
                "v1.12.8".to_string()
            ]
        );
    }

    #[test]
    fn select_asset_uses_exact_target_tarball() {
        let release = Release {
            id: 1,
            tag_name: "v1.13.9".to_string(),
            name: None,
            draft: false,
            prerelease: false,
            html_url: "https://example.com".to_string(),
            published_at: None,
            assets: vec![
                ReleaseAsset {
                    id: 1,
                    name: "sing-box-1.13.9-darwin-arm64.tar.gz".to_string(),
                    content_type: None,
                    size: 1,
                    browser_download_url: "https://example.com/a.tgz".to_string(),
                    download_count: None,
                    updated_at: None,
                },
                ReleaseAsset {
                    id: 2,
                    name: "sing-box-1.13.9-darwin-amd64-legacy-macos-10.13.tar.gz".to_string(),
                    content_type: None,
                    size: 1,
                    browser_download_url: "https://example.com/b.tgz".to_string(),
                    download_count: None,
                    updated_at: None,
                },
            ],
        };
        let asset = select_asset(&release, InstallTarget::DarwinArm64).unwrap();
        assert_eq!(asset.name, "sing-box-1.13.9-darwin-arm64.tar.gz");
    }

    #[test]
    fn normalize_request_path_adds_leading_slash() {
        assert_eq!(
            normalize_request_path("repos/SagerNet/sing-box/releases/latest"),
            "/repos/SagerNet/sing-box/releases/latest"
        );
    }

    #[test]
    fn parse_version_handles_two_segment_tags() {
        let version = parse_version("v1.3-rc2").unwrap();
        assert_eq!(version.major, 1);
        assert_eq!(version.minor, 3);
        assert_eq!(version.patch, 0);
        assert_eq!(version.pre.as_str(), "rc2");
    }

    #[test]
    fn render_release_line_marks_installed_versions() {
        let release = Release {
            id: 1,
            tag_name: "v1.13.9".to_string(),
            name: None,
            draft: false,
            prerelease: false,
            html_url: "https://example.com".to_string(),
            published_at: None,
            assets: vec![],
        };
        let installed_versions = HashSet::from(["v1.13.9".to_string()]);
        assert_eq!(
            render_release_line(&release, &installed_versions, "v1.13.9".len()),
            "* v1.13.9  release"
        );
    }

    #[test]
    fn validate_ls_remote_limit_rejects_invalid_values() {
        assert!(validate_ls_remote_limit(0).is_err());
        assert!(validate_ls_remote_limit(101).is_err());
        assert!(validate_ls_remote_limit(20).is_ok());
    }
}
