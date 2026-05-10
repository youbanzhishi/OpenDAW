//! EEL2内置函数实现
//!
//! 提供JSFX/EEL2脚本可用的数学函数、内存操作、字符串操作等
//! 兼容Reaper JSFX的内置函数集

/// 内置函数枚举
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuiltinFn {
    // 三角函数
    Sin,
    Cos,
    Tan,
    Asin,
    Acos,
    Atan,
    Atan2,
    Sinh,
    Cosh,
    Tanh,
    // 数学函数
    Sqrt,
    Abs,
    Exp,
    Log,
    Log10,
    Floor,
    Ceil,
    Round,
    Sign,
    Min,
    Max,
    Clamp,
    InvSqrt,
    Pow,
    // 随机数
    Srand,
    Rand,
    // 内存操作
    MemGet,
    MemSet,
    MemCpy,
    // 近似
    Near,
    SlToTime,
    // 字符串/格式化
    Sprintf,
    Strlen,
    Strcmp,
    Strcpy,
    Strcat,
    // 时间
    Time,
    TimePrecise,
    // FFT
    Fft,
    Ifft,
    FftSwap,
    FftPermute,
    // MDCT
    Mdct,
    Imdct,
    // 卷积/滤波辅助
    ConvolveC,
    // 其他实用
    Adler32,
    ScanHash,
}

impl BuiltinFn {
    /// 从函数名查找内置函数（大小写不敏感）
    pub fn from_name(name: &str) -> Option<BuiltinFn> {
        match name.to_lowercase().as_str() {
            // 三角函数
            "sin" => Some(BuiltinFn::Sin),
            "cos" => Some(BuiltinFn::Cos),
            "tan" => Some(BuiltinFn::Tan),
            "asin" => Some(BuiltinFn::Asin),
            "acos" => Some(BuiltinFn::Acos),
            "atan" => Some(BuiltinFn::Atan),
            "atan2" => Some(BuiltinFn::Atan2),
            "sinh" => Some(BuiltinFn::Sinh),
            "cosh" => Some(BuiltinFn::Cosh),
            "tanh" => Some(BuiltinFn::Tanh),
            // 数学函数
            "sqrt" => Some(BuiltinFn::Sqrt),
            "abs" => Some(BuiltinFn::Abs),
            "exp" => Some(BuiltinFn::Exp),
            "log" => Some(BuiltinFn::Log),
            "log10" => Some(BuiltinFn::Log10),
            "floor" => Some(BuiltinFn::Floor),
            "ceil" => Some(BuiltinFn::Ceil),
            "round" => Some(BuiltinFn::Round),
            "sign" => Some(BuiltinFn::Sign),
            "min" => Some(BuiltinFn::Min),
            "max" => Some(BuiltinFn::Max),
            "clamp" => Some(BuiltinFn::Clamp),
            "invsqrt" | "rsqrt" => Some(BuiltinFn::InvSqrt),
            "pow" => Some(BuiltinFn::Pow),
            // 随机数
            "srand" => Some(BuiltinFn::Srand),
            "rand" => Some(BuiltinFn::Rand),
            // 内存操作
            "mem_get" => Some(BuiltinFn::MemGet),
            "mem_set" => Some(BuiltinFn::MemSet),
            "mem_cpy" => Some(BuiltinFn::MemCpy),
            // 近似
            "near" => Some(BuiltinFn::Near),
            "sl_to_time" => Some(BuiltinFn::SlToTime),
            // 字符串（简化实现，返回0）
            "sprintf" => Some(BuiltinFn::Sprintf),
            "strlen" => Some(BuiltinFn::Strlen),
            "strcmp" | "strncmp" => Some(BuiltinFn::Strcmp),
            "strcpy" | "strncpy" => Some(BuiltinFn::Strcpy),
            "strcat" | "strncat" => Some(BuiltinFn::Strcat),
            // 时间
            "time" => Some(BuiltinFn::Time),
            "time_precise" => Some(BuiltinFn::TimePrecise),
            // FFT
            "fft" => Some(BuiltinFn::Fft),
            "ifft" => Some(BuiltinFn::Ifft),
            "fft_swap" | "fftswap" => Some(BuiltinFn::FftSwap),
            "fft_permute" | "fftpermute" => Some(BuiltinFn::FftPermute),
            // MDCT
            "mdct" => Some(BuiltinFn::Mdct),
            "imdct" => Some(BuiltinFn::Imdct),
            // 卷积
            "convolve_c" => Some(BuiltinFn::ConvolveC),
            // 其他
            "adler32" => Some(BuiltinFn::Adler32),
            "scanhash" | "scan_hash" => Some(BuiltinFn::ScanHash),
            _ => None,
        }
    }

    /// 返回函数期望的参数数量（最少, 最多）
    pub fn arg_count(&self) -> (usize, usize) {
        match self {
            // 单参数数学函数
            BuiltinFn::Sin | BuiltinFn::Cos | BuiltinFn::Tan
            | BuiltinFn::Asin | BuiltinFn::Acos | BuiltinFn::Atan
            | BuiltinFn::Sinh | BuiltinFn::Cosh | BuiltinFn::Tanh
            | BuiltinFn::Sqrt | BuiltinFn::Abs | BuiltinFn::Exp
            | BuiltinFn::Log | BuiltinFn::Log10
            | BuiltinFn::Floor | BuiltinFn::Ceil | BuiltinFn::Round
            | BuiltinFn::Sign | BuiltinFn::InvSqrt
            | BuiltinFn::Srand | BuiltinFn::Rand
            | BuiltinFn::Near | BuiltinFn::Strlen
            | BuiltinFn::Time | BuiltinFn::TimePrecise
            => (1, 1),

            // 双参数
            BuiltinFn::Atan2 | BuiltinFn::Min | BuiltinFn::Max
            | BuiltinFn::Pow | BuiltinFn::Strcmp
            => (2, 2),

            // 三参数
            BuiltinFn::Clamp => (3, 3),

            // 内存操作
            BuiltinFn::MemGet => (1, 1),
            BuiltinFn::MemSet => (2, 2),
            BuiltinFn::MemCpy => (3, 3),

            // 多参数
            BuiltinFn::SlToTime => (1, 1),
            BuiltinFn::Sprintf => (2, 10),
            BuiltinFn::Strcpy | BuiltinFn::Strcat => (2, 2),

            // FFT系列
            BuiltinFn::Fft | BuiltinFn::Ifft => (2, 2),
            BuiltinFn::FftSwap | BuiltinFn::FftPermute => (2, 2),
            BuiltinFn::Mdct | BuiltinFn::Imdct => (2, 2),
            BuiltinFn::ConvolveC => (4, 4),

            BuiltinFn::Adler32 => (3, 3),
            BuiltinFn::ScanHash => (2, 2),
        }
    }

    /// 执行内置函数
    pub fn call(&self, args: &[f64]) -> f64 {
        match self {
            // 三角函数
            BuiltinFn::Sin => args.first().map(|a| a.sin()).unwrap_or(0.0),
            BuiltinFn::Cos => args.first().map(|a| a.cos()).unwrap_or(0.0),
            BuiltinFn::Tan => args.first().map(|a| a.tan()).unwrap_or(0.0),
            BuiltinFn::Asin => args.first().map(|a| a.asin()).unwrap_or(0.0),
            BuiltinFn::Acos => args.first().map(|a| a.acos()).unwrap_or(0.0),
            BuiltinFn::Atan => args.first().map(|a| a.atan()).unwrap_or(0.0),
            BuiltinFn::Atan2 => {
                let y = args.first().copied().unwrap_or(0.0);
                let x = args.get(1).copied().unwrap_or(1.0);
                y.atan2(x)
            }
            BuiltinFn::Sinh => args.first().map(|a| a.sinh()).unwrap_or(0.0),
            BuiltinFn::Cosh => args.first().map(|a| a.cosh()).unwrap_or(0.0),
            BuiltinFn::Tanh => args.first().map(|a| a.tanh()).unwrap_or(0.0),
            // 数学函数
            BuiltinFn::Sqrt => args.first().map(|a| if *a >= 0.0 { a.sqrt() } else { 0.0 }).unwrap_or(0.0),
            BuiltinFn::Abs => args.first().map(|a| a.abs()).unwrap_or(0.0),
            BuiltinFn::Exp => args.first().map(|a| a.exp()).unwrap_or(1.0),
            BuiltinFn::Log => args.first().map(|a| if *a > 0.0 { a.ln() } else { f64::NEG_INFINITY }).unwrap_or(f64::NEG_INFINITY),
            BuiltinFn::Log10 => args.first().map(|a| if *a > 0.0 { a.log10() } else { f64::NEG_INFINITY }).unwrap_or(f64::NEG_INFINITY),
            BuiltinFn::Floor => args.first().map(|a| a.floor()).unwrap_or(0.0),
            BuiltinFn::Ceil => args.first().map(|a| a.ceil()).unwrap_or(0.0),
            BuiltinFn::Round => args.first().map(|a| a.round()).unwrap_or(0.0),
            BuiltinFn::Sign => args.first().map(|a| a.signum()).unwrap_or(0.0),
            BuiltinFn::Min => {
                let a = args.first().copied().unwrap_or(0.0);
                let b = args.get(1).copied().unwrap_or(0.0);
                a.min(b)
            }
            BuiltinFn::Max => {
                let a = args.first().copied().unwrap_or(0.0);
                let b = args.get(1).copied().unwrap_or(0.0);
                a.max(b)
            }
            BuiltinFn::Clamp => {
                let val = args.first().copied().unwrap_or(0.0);
                let min = args.get(1).copied().unwrap_or(0.0);
                let max = args.get(2).copied().unwrap_or(1.0);
                val.clamp(min, max)
            }
            BuiltinFn::InvSqrt => {
                args.first().map(|a| {
                    if *a > 0.0 { 1.0 / a.sqrt() } else { 0.0 }
                }).unwrap_or(0.0)
            }
            BuiltinFn::Pow => {
                let base = args.first().copied().unwrap_or(0.0);
                let exp = args.get(1).copied().unwrap_or(0.0);
                base.powf(exp)
            }
            // 随机数 — 实际由VM通过runtime.rand_next()处理
            BuiltinFn::Srand => 0.0,
            BuiltinFn::Rand => 0.0,
            // 内存操作 — 在VM中特殊处理
            BuiltinFn::MemGet | BuiltinFn::MemSet | BuiltinFn::MemCpy => 0.0,
            // 近似
            BuiltinFn::Near => {
                let a = args.first().copied().unwrap_or(0.0);
                let b = args.get(1).copied().unwrap_or(0.0);
                if (a - b).abs() < 0.00001 { 1.0 } else { 0.0 }
            }
            BuiltinFn::SlToTime => {
                let samples = args.first().copied().unwrap_or(0.0);
                samples / 44100.0
            }
            // 字符串操作 — 简化返回0
            BuiltinFn::Sprintf | BuiltinFn::Strlen | BuiltinFn::Strcmp
            | BuiltinFn::Strcpy | BuiltinFn::Strcat => 0.0,
            // 时间
            BuiltinFn::Time => {
                use std::time::SystemTime;
                SystemTime::now()
                    .duration_since(SystemTime::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs() as f64
            }
            BuiltinFn::TimePrecise => {
                use std::time::SystemTime;
                SystemTime::now()
                    .duration_since(SystemTime::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs_f64()
            }
            // FFT — 简化实现，返回0（真实FFT需要专门实现）
            BuiltinFn::Fft | BuiltinFn::Ifft | BuiltinFn::FftSwap
            | BuiltinFn::FftPermute | BuiltinFn::Mdct | BuiltinFn::Imdct
            | BuiltinFn::ConvolveC => 0.0,
            // 其他
            BuiltinFn::Adler32 | BuiltinFn::ScanHash => 0.0,
        }
    }
}
