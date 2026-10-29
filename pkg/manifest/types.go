package manifest

// ToolchainManifest represents the dynamic toolchain definition.
type ToolchainManifest struct {
	Version      string          `json:"version"`
	ReleaseDate  string          `json:"release_date"`
	MinEngine    string          `json:"min_fway_engine"`
	Flutter      FlutterConfig   `json:"flutter"`
	JDK          JDKConfig       `json:"jdk"`
	Android      AndroidConfig   `json:"android"`
	Gradle       GradleConfig    `json:"gradle"`
	DoctorRules  []DoctorRule    `json:"doctor_rules"`
}

type FlutterConfig struct {
	RecommendedChannel string                    `json:"recommended_channel"`
	Channels           map[string]FlutterChannel `json:"channels"`
}

type FlutterChannel struct {
	Version               string `json:"version"`
	URL                   string `json:"url"`
	MirrorURL             string `json:"mirror_url"`
	SHA256                string `json:"sha256"`
	MinJDK                int    `json:"min_jdk"`
	MaxJDK                int    `json:"max_jdk"`
	RecommendedAndroidAPI int    `json:"recommended_android_api"`
	RecommendedBuildTools string `json:"recommended_build_tools"`
}

type JDKConfig struct {
	Provider  string `json:"provider"`
	Version   string `json:"version"`
	URL       string `json:"url"`
	SHA256    string `json:"sha256"`
	SystemVar string `json:"system_var"`
}

type AndroidConfig struct {
	CmdlineTools CmdlineToolsConfig          `json:"cmdline_tools"`
	Profiles     map[string]AndroidProfile   `json:"profiles"`
}

type CmdlineToolsConfig struct {
	Version        string `json:"version"`
	URL            string `json:"url"`
	MirrorURL      string `json:"mirror_url"`
	SHA256         string `json:"sha256"`
	TargetSubfolder string `json:"target_subfolder"`
}

type AndroidProfile struct {
	Description        string   `json:"description"`
	Packages           []string `json:"packages"`
	EstimatedDownloadMB int     `json:"estimated_download_mb"`
}

type GradleConfig struct {
	GlobalTuning GradleTuning `json:"global_tuning"`
}

type GradleTuning struct {
	Daemon           bool   `json:"daemon"`
	Parallel         bool   `json:"parallel"`
	Caching          bool   `json:"caching"`
	JVMArgsLowRAM    string `json:"jvmargs_low_ram"`
	JVMArgsHighRAM   string `json:"jvmargs_high_ram"`
	WindowsRootCAFix bool   `json:"windows_root_ca_fix"`
}

type DoctorRule struct {
	ID            string `json:"id"`
	Category      string `json:"category"`
	Severity      string `json:"severity"`
	Pattern       string `json:"pattern"`
	TitleAR       string `json:"title_ar"`
	TitleEN       string `json:"title_en"`
	DescriptionAR string `json:"description_ar"`
	AutoFixable   bool   `json:"auto_fixable"`
	FixAction     string `json:"fix_action"`
}
