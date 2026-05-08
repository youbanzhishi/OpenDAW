//! EEL2内置函数实现
//!
//! 提供JSFX/EEL2脚本可用的数学函数、内存操作等

/// 内置函数枚举
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuiltinFn {
    // 数学函数
    Sin,
    Cos,
    Tan,
    Asin,
    Acos,
    Atan,
    Atan2,
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
}

impl BuiltinFn {
    /// 从函数名查找内置函数（大小写不敏感）
    pub fn from_name(name: &str) -> Option<BuiltinFn> {
        match name.to_lowercase().as_str() {
            "sin" => Some(BuiltinFn::Sin),
            "cos" => Some(BuiltinFn::Cos),
            "tan" => Some(BuiltinFn::Tan),
            "asin" => Some(BuiltinFn::Asin),
            "acos" => Some(BuiltinFn::Acos),
            "atan" => Some(BuiltinFn::Atan),
            "atan2" => Some(BuiltinFn::Atan2),
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
            "srand" => Some(BuiltinFn::Srand),
            "rand" => Some(BuiltinFn::Rand),
            "mem_get" => Some(BuiltinFn::MemGet),
            "mem_set" => Some(BuiltinFn::MemSet),
            "mem_cpy" => Some(BuiltinFn::MemCpy),
            "near" => Some(BuiltinFn::Near),
            "sl_to_time" => Some(BuiltinFn::SlToTime),
            _ => None,
        }
    }

    /// 返回函数期望的参数数量（最少, 最多）
    pub fn arg_count(&self) -> (usize, usize) {
        match self {
            BuiltinFn::Sin | BuiltinFn::Cos | BuiltinFn::Tan
            | BuiltinFn::Asin | BuiltinFn::Acos | BuiltinFn::Atan
            | BuiltinFn::Sqrt | BuiltinFn::Abs | BuiltinFn::Exp
            | BuiltinFn::Log | BuiltinFn::Log10
            | BuiltinFn::Floor | BuiltinFn::Ceil | BuiltinFn::Round
            | BuiltinFn::Sign | BuiltinFn::InvSqrt
            | BuiltinFn::Srand | BuiltinFn::Rand
            | BuiltinFn::Near => (1, 1),

            BuiltinFn::Atan2 | BuiltinFn::Min | BuiltinFn::Max
            | BuiltinFn::Pow => (2, 2),

            BuiltinFn::Clamp => (3, 3),

            BuiltinFn::MemGet => (1, 1),
            BuiltinFn::MemSet => (2, 2),
            BuiltinFn::MemCpy => (3, 3),
            BuiltinFn::SlToTime => (1, 1),
        }
    }

    /// 执行内置函数
    pub fn call(&self, args: &[f64]) -> f64 {
        match self {
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
            BuiltinFn::Srand => {
                // 设置随机种子（简化：直接返回0）
                0.0
            }
            BuiltinFn::Rand => {
                // 返回[0,1)随机数（简化实现）
                // 使用简单的LCG伪随机
                use std::time::SystemTime;
                let t = SystemTime::now()
                    .duration_since(SystemTime::UNIX_EPOCH)
                    .unwrap_or_default()
                    .subsec_nanos();
                ((t as u64).wrapping_mul(6364136223846793005) >> 33) as f64 / 2147483648.0
            }
            BuiltinFn::MemGet | BuiltinFn::MemSet | BuiltinFn::MemCpy => {
                // 内存操作在VM中特殊处理，这里不应被调用
                0.0
            }
            BuiltinFn::Near => {
                let a = args.first().copied().unwrap_or(0.0);
                let b = args.get(1).copied().unwrap_or(0.0);
                if (a - b).abs() < 0.00001 { 1.0 } else { 0.0 }
            }
            BuiltinFn::SlToTime => {
                // 简化：将采样位置转为秒
                let samples = args.first().copied().unwrap_or(0.0);
                samples / 44100.0
            }
        }
    }
}
